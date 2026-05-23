"""
PlanningStage — the planner loop.

For each iteration:
    1. Ask Planner for the next NextStep.
    2. Record step into RuntimeTurnState + emit a PLANNER_STEP event.
    3. Dispatch on kind:
         CALL_AGENT → AgentExecutionPort.execute(...) → stream events
         ASK_USER   → terminal (waiting_input)
         FINAL      → terminal (completed) — finalization runs next
         ABORT      → terminal (aborted)
    4. Loop detection → terminal (loop_detected).
    5. Max-iters   → terminal (max_iters).

The stage does not finalize by itself; it reports a PlanningOutcome and
FinalizationStage handles synthesizer + rolling summary + terminal persist.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import UUID, uuid4

from app.agents.context import ToolContext
from app.core.logging import get_logger
from app.runtime.budgets import BudgetRegistry, BudgetResolver, BudgetExceededError
from app.runtime.contracts import (
    NextStepKind,
    PipelineRequest,
    PipelineStopReason,
)
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
from app.runtime.llm.limits import LLMLimitExceededError
from app.runtime.operation_errors import RuntimeErrorCode
from app.runtime.ports import (
    AgentExecutionPort,
    PlannerServicePort,
)
from app.runtime.turn_state import RuntimeTurnState

logger = get_logger(__name__)


class PlanningOutcomeKind(str, Enum):
    NEEDS_FINAL = "needs_final"        # synthesizer should run
    DIRECT = "direct"                  # planner answered directly; final already emitted
    PAUSED = "paused"                  # ASK_USER / CLARIFY — stop, no synth
    ABORTED = "aborted"                # planner-driven abort
    FAILED = "failed"                  # planner raised


@dataclass
class PlanningOutcome:
    kind: PlanningOutcomeKind
    stop_reason: PipelineStopReason
    planner_hint: Optional[str] = None      # final_answer hint from planner
    error_message: Optional[str] = None


class PlanningStage:
    """Runs the planner loop. Dispatches to AgentExecutionPort for CALL_AGENT."""

    def __init__(
        self,
        *,
        planner: PlannerServicePort,
        agent_executor: AgentExecutionPort,
        max_iterations: int,
    ) -> None:
        self._planner = planner
        self._agent = agent_executor
        self._max_iterations = max_iterations
        self.outcome: Optional[PlanningOutcome] = None

    async def run(
        self,
        *,
        runtime_state: RuntimeTurnState,
        request: PipelineRequest,
        ctx: ToolContext,
        user_id: UUID,
        tenant_id: UUID,
        available_agents: List[Dict[str, Any]],
        platform_config: Dict[str, Any],
        orchestrator_id: Optional[str] = None,
    ) -> AsyncIterator[PhasedEvent]:
        run_id = runtime_state.run_id
        chat_id = runtime_state.chat_id
        runtime_state.goal = runtime_state.goal or request.request_text
        runtime_state.current_user_query = request.request_text
        planner_agents: List[Dict[str, Any]] = list(available_agents or [])
        planner_run_id = str(run_id)
        effective_orchestrator_id = orchestrator_id or f"{run_id}:orchestrator"
        budget_registry = ctx.extra.get("runtime_budget_registry")
        planner_registry = budget_registry if isinstance(budget_registry, BudgetRegistry) else None
        budget_resolver = ctx.extra.get("runtime_budget_resolver")
        planner_limits = None
        if isinstance(budget_resolver, BudgetResolver):
            planner_limits = await budget_resolver.resolve_orchestrator("planner")
        if planner_registry is not None:
            planner_registry.register(
                entity_type="orchestrator",
                entity_id=effective_orchestrator_id,
                parent_entity_id=str(run_id),
                role="planner",
                limits=planner_limits,
            )
            init_payload = planner_registry.emit_snapshot(effective_orchestrator_id, reason="init") or {}
            yield PhasedEvent(
                RuntimeEvent.budget_snapshot(
                    entity_type="orchestrator",
                    entity_id=effective_orchestrator_id,
                    parent_entity_type="run",
                    parent_entity_id=str(run_id),
                    role="planner",
                    own=init_payload.get("own", {}),
                    limits=init_payload.get("limits"),
                    delta={},
                    reason="init",
                    at_ms=init_payload.get("at_ms"),
                ),
                OrchestrationPhase.PLANNER,
            )

        while runtime_state.iter_count < self._max_iterations:
            planner_iteration = runtime_state.iter_count + 1
            planner_iteration_id = f"{planner_run_id}:planner:{planner_iteration}"
            planner_event_ctx = {
                "planner_run_id": planner_run_id,
                "planner_iteration_id": planner_iteration_id,
                "iteration": planner_iteration,
            }
            yield PhasedEvent(
                RuntimeEvent.planner_iteration_start(
                    iteration_id=planner_iteration_id,
                    orchestrator_id=effective_orchestrator_id,
                    iteration=planner_iteration,
                ),
                OrchestrationPhase.PLANNER,
            )
            if planner_registry is not None:
                try:
                    planner_registry.consume(
                        effective_orchestrator_id,
                        "planner_steps",
                        1,
                        reason="step",
                    )
                except BudgetExceededError as exc:
                    runtime_state.status = PipelineStopReason.FAILED.value
                    runtime_state.final_error = f"budget_exceeded: {exc.metric}"
                    yield PhasedEvent(
                        RuntimeEvent.error(
                            f"Planner budget exceeded: {exc.metric}",
                            recoverable=False,
                            parent_entity_type="orchestrator",
                            parent_entity_id=effective_orchestrator_id,
                        ),
                        OrchestrationPhase.PLANNER,
                    )
                    self.outcome = PlanningOutcome(
                        kind=PlanningOutcomeKind.FAILED,
                        stop_reason=PipelineStopReason.FAILED,
                        error_message=str(exc),
                    )
                    return
                planner_payload = planner_registry.emit_snapshot(
                    effective_orchestrator_id,
                    reason="step",
                    delta={"planner_steps": 1},
                ) or {}
                yield PhasedEvent(
                    RuntimeEvent.budget_snapshot(
                        entity_type="orchestrator",
                        entity_id=effective_orchestrator_id,
                        parent_entity_type="run",
                        parent_entity_id=str(run_id),
                        role="planner",
                        own=planner_payload.get("own", {}),
                        limits=planner_payload.get("limits"),
                        delta={"planner_steps": 1},
                        reason="step",
                        at_ms=planner_payload.get("at_ms"),
                    ),
                    OrchestrationPhase.PLANNER,
                )

            try:
                planner_result = await self._planner.next_step(
                    runtime_state=runtime_state,
                    available_agents=planner_agents,
                    outline=runtime_state.outline,
                    platform_config=platform_config,
                    chat_id=chat_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_run_id=run_id,
                    planner_iteration_id=planner_event_ctx["planner_iteration_id"],
                )
                if isinstance(planner_result, tuple):
                    step = planner_result[0]
                    planner_llm_trace = planner_result[1] if len(planner_result) > 1 else None
                else:
                    step = planner_result
                    planner_llm_trace = None
            except Exception as exc:
                logger.error(
                    "Planner failure on iter=%s: %s", runtime_state.iter_count, exc, exc_info=True
                )
                error_code = None
                if isinstance(exc, LLMLimitExceededError):
                    error_code = exc.code
                runtime_state.status = PipelineStopReason.FAILED.value
                runtime_state.final_error = f"planner_exception: {exc}"
                yield PhasedEvent(
                    RuntimeEvent.error(f"Planner failed: {exc}", recoverable=False,
                                       error_code=error_code,
                                       parent_entity_type="planner_iteration",
                                       parent_entity_id=planner_iteration_id),
                    OrchestrationPhase.PLANNER,
                )
                yield PhasedEvent(
                    RuntimeEvent.planner_iteration_end(
                        iteration_id=planner_iteration_id,
                        orchestrator_id=effective_orchestrator_id,
                        iteration=planner_iteration,
                        status="failed",
                    ),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.FAILED,
                    stop_reason=PipelineStopReason.FAILED,
                    error_message=str(exc),
                )
                return

            if planner_llm_trace is not None:
                llm_parent_id = planner_event_ctx["planner_iteration_id"]
                yield PhasedEvent(
                    RuntimeEvent.llm_request(
                        llm_call_id=planner_llm_trace.llm_call_id,
                        model=planner_llm_trace.model,
                        messages=[
                            {"role": "user", "content": planner_llm_trace.request_payload},
                        ],
                        parent_entity_type="planner_iteration",
                        parent_entity_id=llm_parent_id,
                        planner_iteration_id=llm_parent_id,
                        planner_run_id=planner_event_ctx["planner_run_id"],
                        purpose="planning_decision",
                    ),
                    OrchestrationPhase.PLANNER,
                )
                yield PhasedEvent(
                    RuntimeEvent.llm_response(
                        llm_call_id=planner_llm_trace.llm_call_id,
                        model=planner_llm_trace.model,
                        content=planner_llm_trace.raw_response,
                        response_length=planner_llm_trace.response_length,
                        parent_entity_type="planner_iteration",
                        parent_entity_id=llm_parent_id,
                        planner_iteration_id=llm_parent_id,
                        planner_run_id=planner_event_ctx["planner_run_id"],
                    ),
                    OrchestrationPhase.PLANNER,
                )
                yield PhasedEvent(
                    RuntimeEvent.llm_call(
                        llm_call_id=planner_llm_trace.llm_call_id,
                        model=planner_llm_trace.model,
                        response_length=planner_llm_trace.response_length,
                        tokens_in=planner_llm_trace.tokens_in,
                        tokens_out=planner_llm_trace.tokens_out,
                        tokens_total=planner_llm_trace.tokens_total,
                        duration_ms=planner_llm_trace.duration_ms,
                        parent_entity_type="planner_iteration",
                        parent_entity_id=llm_parent_id,
                        planner_iteration_id=llm_parent_id,
                        planner_run_id=planner_event_ctx["planner_run_id"],
                        purpose="planning_decision",
                    ),
                    OrchestrationPhase.PLANNER,
                )
                if planner_registry is not None:
                    try:
                        if planner_llm_trace.tokens_in > 0:
                            planner_registry.consume(
                                effective_orchestrator_id,
                                "tokens_in",
                                planner_llm_trace.tokens_in,
                                reason="tokens",
                            )
                        if planner_llm_trace.tokens_out > 0:
                            planner_registry.consume(
                                effective_orchestrator_id,
                                "tokens_out",
                                planner_llm_trace.tokens_out,
                                reason="tokens",
                            )
                        if planner_llm_trace.tokens_total > 0:
                            planner_registry.consume(
                                effective_orchestrator_id,
                                "tokens_total",
                                planner_llm_trace.tokens_total,
                                reason="tokens",
                            )
                        if planner_llm_trace.duration_ms > 0:
                            planner_registry.consume(
                                effective_orchestrator_id,
                                "wall_time_ms",
                                planner_llm_trace.duration_ms,
                                reason="wall_time",
                            )
                    except BudgetExceededError as exc:
                        runtime_state.status = PipelineStopReason.FAILED.value
                        runtime_state.final_error = f"budget_exceeded: {exc.metric}"
                        yield PhasedEvent(
                            RuntimeEvent.error(
                                f"Planner budget exceeded: {exc.metric}",
                                recoverable=False,
                                parent_entity_type="orchestrator",
                                parent_entity_id=effective_orchestrator_id,
                            ),
                            OrchestrationPhase.PLANNER,
                        )
                        self.outcome = PlanningOutcome(
                            kind=PlanningOutcomeKind.FAILED,
                            stop_reason=PipelineStopReason.FAILED,
                            error_message=str(exc),
                        )
                        return
                    planner_tokens_delta: Dict[str, int] = {}
                    if planner_llm_trace.tokens_in > 0:
                        planner_tokens_delta["tokens_in"] = planner_llm_trace.tokens_in
                    if planner_llm_trace.tokens_out > 0:
                        planner_tokens_delta["tokens_out"] = planner_llm_trace.tokens_out
                    if planner_llm_trace.tokens_total > 0:
                        planner_tokens_delta["tokens_total"] = planner_llm_trace.tokens_total
                    if planner_llm_trace.duration_ms > 0:
                        planner_tokens_delta["wall_time_ms"] = planner_llm_trace.duration_ms
                    if planner_tokens_delta:
                        planner_payload = planner_registry.emit_snapshot(
                            effective_orchestrator_id,
                            reason="tokens",
                            delta=planner_tokens_delta,
                        ) or {}
                        yield PhasedEvent(
                            RuntimeEvent.budget_snapshot(
                                entity_type="orchestrator",
                                entity_id=effective_orchestrator_id,
                                parent_entity_type="run",
                                parent_entity_id=str(run_id),
                                role="planner",
                                own=planner_payload.get("own", {}),
                                limits=planner_payload.get("limits"),
                                delta=planner_tokens_delta,
                                reason="tokens",
                                at_ms=planner_payload.get("at_ms"),
                            ),
                            OrchestrationPhase.PLANNER,
                        )

            step_record = {
                "iteration": planner_iteration,
                "kind": step.kind.value,
                "agent_slug": step.agent_slug,
                "phase_id": step.phase_id,
                "rationale": step.rationale,
                "agent_input": step.agent_input or {},
            }
            runtime_state.add_planner_step(step_record)

            yield PhasedEvent(
                RuntimeEvent.planner_step(
                    iteration=runtime_state.iter_count,
                    kind=step.kind.value,
                    payload={
                        **planner_event_ctx,
                        "parent_entity_type": "planner_iteration",
                        "parent_entity_id": planner_iteration_id,
                        "planner_iteration_id": planner_iteration_id,
                        "agent_slug": step.agent_slug,
                        "rationale": step.rationale,
                        "phase_id": step.phase_id,
                        "risk": step.risk,
                    },
                ),
                OrchestrationPhase.PLANNER,
            )

            # Loop detection is driven by sub-agent action signatures, not
            # planner records — check after agent execution below.

            # --- Dispatch -------------------------------------------------
            if step.kind == NextStepKind.DIRECT_ANSWER:
                # Planner answered without touching any agent (small-talk,
                # chitchat, purely-knowledge reply). Stream its text verbatim
                # as a single delta + final; no synthesizer roundtrip.
                answer = (step.final_answer or "").strip()
                runtime_state.final_answer = answer
                runtime_state.status = PipelineStopReason.COMPLETED.value
                if answer:
                    yield PhasedEvent(
                        RuntimeEvent.delta(answer),
                        OrchestrationPhase.SYNTHESIS,
                    )
                yield PhasedEvent(
                    RuntimeEvent.final(
                        answer, sources=[], run_id=str(run_id),
                    ),
                    OrchestrationPhase.SYNTHESIS,
                )
                yield PhasedEvent(
                    RuntimeEvent.planner_iteration_end(
                        iteration_id=planner_iteration_id,
                        orchestrator_id=effective_orchestrator_id,
                        iteration=planner_iteration,
                        status="completed",
                    ),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.DIRECT,
                    stop_reason=PipelineStopReason.COMPLETED,
                    planner_hint=answer,
                )
                return

            if step.kind == NextStepKind.FINAL:
                runtime_state.status = PipelineStopReason.COMPLETED.value
                yield PhasedEvent(
                    RuntimeEvent.planner_iteration_end(
                        iteration_id=planner_iteration_id,
                        orchestrator_id=effective_orchestrator_id,
                        iteration=planner_iteration,
                        status="completed",
                    ),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.NEEDS_FINAL,
                    stop_reason=PipelineStopReason.COMPLETED,
                    planner_hint=step.final_answer,
                )
                return

            if step.kind in (NextStepKind.ASK_USER, NextStepKind.CLARIFY):
                question = step.question or "Нужны дополнительные данные для продолжения."
                if question not in runtime_state.open_questions:
                    runtime_state.open_questions.append(question)
                runtime_state.status = PipelineStopReason.WAITING_INPUT.value
                yield PhasedEvent(
                    RuntimeEvent.waiting_input(question, run_id=str(run_id)),
                    OrchestrationPhase.PLANNER,
                )
                yield PhasedEvent(
                    RuntimeEvent.stop(
                        PipelineStopReason.WAITING_INPUT.value,
                        run_id=str(run_id),
                        question=question,
                    ),
                    OrchestrationPhase.PLANNER,
                )
                yield PhasedEvent(
                    RuntimeEvent.planner_iteration_end(
                        iteration_id=planner_iteration_id,
                        orchestrator_id=effective_orchestrator_id,
                        iteration=planner_iteration,
                        status="paused",
                    ),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.PAUSED,
                    stop_reason=PipelineStopReason.WAITING_INPUT,
                )
                return

            if step.kind == NextStepKind.ABORT:
                runtime_state.status = PipelineStopReason.ABORTED.value
                runtime_state.final_error = step.rationale
                yield PhasedEvent(
                    RuntimeEvent.error(f"Aborted: {step.rationale}", recoverable=False,
                                       parent_entity_type="planner_iteration",
                                       parent_entity_id=planner_iteration_id),
                    OrchestrationPhase.PLANNER,
                )
                yield PhasedEvent(
                    RuntimeEvent.planner_iteration_end(
                        iteration_id=planner_iteration_id,
                        orchestrator_id=effective_orchestrator_id,
                        iteration=planner_iteration,
                        status="aborted",
                    ),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.ABORTED,
                    stop_reason=PipelineStopReason.ABORTED,
                    error_message=step.rationale,
                )
                return

            # kind == CALL_AGENT
            _agent_version_id = self._resolve_agent_version_override(request)
            _agent_run_id_for_lifecycle = str(uuid4())
            _agent_start_emitted = False

            def _ensure_agent_start() -> str:
                nonlocal _agent_start_emitted
                if not _agent_start_emitted:
                    yield_event = RuntimeEvent.agent_start(
                        agent_run_id=_agent_run_id_for_lifecycle,
                        parent_entity_id=planner_iteration_id,
                        parent_entity_type="planner_iteration",
                        agent_slug=step.agent_slug or "unknown",
                    )
                    _agent_start_emitted = True
                    return yield_event
                return None  # type: ignore[return-value]

            _agent_final_status = "completed"
            async for event in self._agent.execute(
                step=step,
                runtime_state=runtime_state,
                messages=request.messages,
                ctx=ctx,
                user_id=user_id,
                tenant_id=tenant_id,
                platform_config=platform_config,
                model=request.model,
                agent_version_id=_agent_version_id,
                lifecycle_agent_run_id=_agent_run_id_for_lifecycle,
            ):
                start_event = _ensure_agent_start()
                if start_event is not None:
                    yield PhasedEvent(start_event, OrchestrationPhase.AGENT)
                if event.type == RuntimeEventType.ERROR:
                    _agent_final_status = "failed"
                yield PhasedEvent(event, OrchestrationPhase.AGENT)
                if event.type == RuntimeEventType.CONFIRMATION_REQUIRED:
                    runtime_state.status = PipelineStopReason.WAITING_CONFIRMATION.value
                    message = str(event.data.get("summary") or event.data.get("message") or "").strip() or None
                    # Include confirmation details in STOP so paused_action has
                    # operation_fingerprint available for resume token issuance (P0-5).
                    stop_event_data: Dict[str, Any] = {
                        "reason": PipelineStopReason.WAITING_CONFIRMATION.value,
                        "run_id": str(run_id),
                    }
                    if message:
                        stop_event_data["message"] = message
                    for _key in ("operation_fingerprint", "tool_slug", "operation", "risk_level", "args_preview", "summary"):
                        _val = event.data.get(_key)
                        if _val is not None:
                            stop_event_data[_key] = _val
                    yield PhasedEvent(
                        RuntimeEvent(RuntimeEventType.STOP, stop_event_data),
                        OrchestrationPhase.PLANNER,
                    )
                    yield PhasedEvent(
                        RuntimeEvent.agent_end(
                            agent_run_id=_agent_run_id_for_lifecycle,
                            parent_entity_id=planner_iteration_id,
                            parent_entity_type="planner_iteration",
                            agent_slug=step.agent_slug or "unknown",
                            status="paused",
                        ),
                        OrchestrationPhase.AGENT,
                    )
                    yield PhasedEvent(
                        RuntimeEvent.planner_iteration_end(
                            iteration_id=planner_iteration_id,
                            orchestrator_id=effective_orchestrator_id,
                            iteration=planner_iteration,
                            status="paused",
                        ),
                        OrchestrationPhase.PLANNER,
                    )
                    self.outcome = PlanningOutcome(
                        kind=PlanningOutcomeKind.PAUSED,
                        stop_reason=PipelineStopReason.WAITING_CONFIRMATION,
                    )
                    return

            if not _agent_start_emitted:
                yield PhasedEvent(
                    RuntimeEvent.agent_start(
                        agent_run_id=_agent_run_id_for_lifecycle,
                        parent_entity_id=planner_iteration_id,
                        parent_entity_type="planner_iteration",
                        agent_slug=step.agent_slug or "unknown",
                    ),
                    OrchestrationPhase.AGENT,
                )
                _agent_start_emitted = True

            # Early degrade path: sub-agent failed with a known hard
            # token/payload limit error. Additional planner iterations usually
            # repeat the same failing call and add overhead.
            if self._last_agent_unavailable(runtime_state, step.agent_slug):
                removed = self._remove_agent(planner_agents, step.agent_slug)
                if removed:
                    yield PhasedEvent(
                        RuntimeEvent.status(
                            "planner_agent_removed_unavailable",
                            **planner_event_ctx,
                            agent=step.agent_slug,
                            remaining_agents=len(planner_agents),
                        ),
                        OrchestrationPhase.PLANNER,
                    )
            yield PhasedEvent(
                RuntimeEvent.agent_end(
                    agent_run_id=_agent_run_id_for_lifecycle,
                    parent_entity_id=planner_iteration_id,
                    parent_entity_type="planner_iteration",
                    agent_slug=step.agent_slug or "unknown",
                    status=_agent_final_status,
                ),
                OrchestrationPhase.AGENT,
            )

            if self._has_non_retryable_agent_failure(runtime_state, step.agent_slug):
                runtime_state.add_runtime_fact(
                    "Agent failed with non-retryable runtime error; finalizing from collected facts.",
                    source="pipeline",
                )
                yield PhasedEvent(
                    RuntimeEvent.status("agent_non_retryable_failure_finalize", **planner_event_ctx),
                    OrchestrationPhase.PLANNER,
                )
                yield PhasedEvent(
                    RuntimeEvent.planner_iteration_end(
                        iteration_id=planner_iteration_id,
                        orchestrator_id=effective_orchestrator_id,
                        iteration=planner_iteration,
                        status="failed",
                    ),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.NEEDS_FINAL,
                    stop_reason=PipelineStopReason.FAILED,
                    planner_hint=None,
                )
                return

            loop_threshold = 3
            if runtime_state.detect_loop(threshold=loop_threshold):
                runtime_state.add_runtime_fact(
                    "Loop detected by runtime; synthesizing from facts.",
                    source="pipeline",
                )
                yield PhasedEvent(
                    RuntimeEvent.status("loop_detected", **planner_event_ctx),
                    OrchestrationPhase.PLANNER,
                )
                yield PhasedEvent(
                    RuntimeEvent.planner_iteration_end(
                        iteration_id=planner_iteration_id,
                        orchestrator_id=effective_orchestrator_id,
                        iteration=planner_iteration,
                        status="loop_detected",
                    ),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.NEEDS_FINAL,
                    stop_reason=PipelineStopReason.LOOP_DETECTED,
                    planner_hint=None,
                )
                return

            yield PhasedEvent(
                RuntimeEvent.planner_iteration_end(
                    iteration_id=planner_iteration_id,
                    orchestrator_id=effective_orchestrator_id,
                    iteration=planner_iteration,
                    status="completed",
                ),
                OrchestrationPhase.PLANNER,
            )

        # Max iterations reached → synthesize whatever we have.
        yield PhasedEvent(
            RuntimeEvent.status(
                "max_iters_reached",
                planner_run_id=planner_run_id,
                planner_iteration_id=f"{planner_run_id}:planner:{runtime_state.iter_count}",
                iterations=runtime_state.iter_count,
            ),
            OrchestrationPhase.PLANNER,
        )
        runtime_state.status = PipelineStopReason.MAX_ITERS.value
        self.outcome = PlanningOutcome(
            kind=PlanningOutcomeKind.NEEDS_FINAL,
            stop_reason=PipelineStopReason.MAX_ITERS,
            planner_hint=None,
        )

    @staticmethod
    def _resolve_agent_version_override(request: PipelineRequest) -> Optional[UUID]:
        # Contract: explicit version pinning is allowed only for sandbox/non-chat
        # execution. Regular chat runtime should use the published/main agent version.
        if request.chat_id is not None:
            return None
        if not request.agent_version_id:
            return None
        try:
            return UUID(str(request.agent_version_id))
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _has_non_retryable_agent_failure(memory_or_state, agent_slug: Optional[str]) -> bool:
        results = list(getattr(memory_or_state, "agent_results", []) or [])
        if not results:
            return False
        last = results[-1]
        if isinstance(last, dict):
            last_slug = str(last.get("agent_slug") or last.get("agent") or "")
            success = bool(last.get("success", True))
            retryable = last.get("retryable")
            error_code = str(last.get("error_code") or "")
        else:
            last_slug = str(getattr(last, "agent_slug", "") or "")
            success = bool(getattr(last, "success", True))
            retryable = getattr(last, "retryable", None)
            error_code = str(getattr(last, "error_code", "") or "")
        if agent_slug and last_slug != agent_slug:
            return False
        if success:
            return False
        if retryable is False:
            return True
        non_retryable_codes = {
            RuntimeErrorCode.OPERATION_UNAVAILABLE.value,
            RuntimeErrorCode.OPERATION_AMBIGUOUS.value,
            RuntimeErrorCode.AGENT_NON_RETRYABLE_OPERATION_FAILURE.value,
            RuntimeErrorCode.AGENT_REQUIRED_OPERATION_CALL_MISSING.value,
            RuntimeErrorCode.AGENT_MAX_TOOL_CALLS_EXCEEDED.value,
            RuntimeErrorCode.AGENT_WALL_TIME_EXCEEDED.value,
            RuntimeErrorCode.AGENT_PRECHECK_FAILED.value,
            RuntimeErrorCode.AGENT_UNAVAILABLE.value,
            RuntimeErrorCode.AGENT_NO_OPERATIONS.value,
        }
        return error_code in non_retryable_codes

    @staticmethod
    def _last_agent_unavailable(memory_or_state, agent_slug: Optional[str]) -> bool:
        results = list(getattr(memory_or_state, "agent_results", []) or [])
        if not results:
            return False
        last = results[-1]
        if isinstance(last, dict):
            last_slug = str(last.get("agent_slug") or last.get("agent") or "")
            success = bool(last.get("success", True))
            error_code = str(last.get("error_code") or "")
        else:
            last_slug = str(getattr(last, "agent_slug", "") or "")
            success = bool(getattr(last, "success", True))
            error_code = str(getattr(last, "error_code", "") or "")
        if agent_slug and last_slug != agent_slug:
            return False
        if success:
            return False
        return error_code in {
            RuntimeErrorCode.AGENT_PRECHECK_FAILED.value,
            RuntimeErrorCode.AGENT_UNAVAILABLE.value,
            RuntimeErrorCode.AGENT_NO_OPERATIONS.value,
        }

    @staticmethod
    def _remove_agent(
        available_agents: List[Dict[str, Any]],
        agent_slug: Optional[str],
    ) -> bool:
        if not agent_slug or not available_agents:
            return False
        before = len(available_agents)
        available_agents[:] = [
            item
            for item in available_agents
            if str((item or {}).get("slug") or "").strip() != agent_slug
        ]
        return len(available_agents) != before
