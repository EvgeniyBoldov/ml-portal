"""
PlanningStage — the planner loop.

For each iteration:
    1. Ask Planner for the next NextStep.
    2. Record step into RuntimeTurnState + emit a PLANNER_STEP event.
    3. Dispatch on kind:
         CALL_AGENT → AgentExecutionPort.execute(...) → stream events
         ASK_USER   → terminal (waiting_input)
         CLARIFY    → terminal (waiting_input)
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
from typing import Any, AsyncIterator, Dict, List, Literal, Optional
from uuid import UUID

from app.agents.context import ToolContext
from app.core.logging import get_logger
from app.runtime.budgets import BudgetRegistry, BudgetResolver
from app.runtime.contracts import (
    ExecutionMode,
    NextStep,
    NextStepKind,
    PipelineRequest,
    PipelineStopReason,
)
from app.runtime.context_snapshot import compact_snapshot, serialize_limits
from app.runtime.envelope import PhasedEvent
from app.runtime.entity_ids import planner_orchestrator_id
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
from app.runtime.stages.planner_call_agent_dispatcher import PlannerCallAgentDispatcher
from app.runtime.stages.planner_budget_guard import PlannerBudgetGuard
from app.runtime.stages.planner_budget_initializer import PlannerBudgetInitializer
from app.runtime.stages.planner_failure_handler import PlannerFailureHandler
from app.runtime.stages.planner_llm_trace_emitter import PlannerLLMTraceEmitter
from app.runtime.stages.planner_next_step_invoker import PlannerNextStepInvoker
from app.runtime.stages.planner_post_call_arbiter import PlannerPostCallArbiter
from app.runtime.stages.planner_step_emitter import PlannerStepEmitter
from app.runtime.stages.planner_step_dispatcher import PlannerStepDispatcher
from app.runtime.stages.planning_outcome_mapper import PlanningOutcomeMapper
from app.runtime.ports import (
    AgentExecutionPort,
    PlannerServicePort,
)
from app.runtime.turn_state import RuntimeTurnState

logger = get_logger(__name__)


class PlanningOutcomeKind(str, Enum):
    NEEDS_FINAL = "needs_final"        # synthesizer should run
    PAUSED = "paused"                  # ASK_USER / CLARIFY — stop, no synth
    ABORTED = "aborted"                # planner-driven abort
    FAILED = "failed"                  # planner raised


@dataclass
class PlanningOutcome:
    kind: PlanningOutcomeKind
    stop_reason: PipelineStopReason
    answer_brief: Optional[str] = None
    final_answer_strategy: Literal["synthesize", "verbatim", "use_agent_result"] = "synthesize"
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
        effective_orchestrator_id = orchestrator_id or planner_orchestrator_id(str(run_id))
        budget_registry = ctx.extra.get("runtime_budget_registry")
        planner_registry = budget_registry if isinstance(budget_registry, BudgetRegistry) else None
        budget_resolver = ctx.extra.get("runtime_budget_resolver")
        planner_limits = None
        if isinstance(budget_resolver, BudgetResolver):
            planner_limits = await budget_resolver.resolve_orchestrator("planner", request.sandbox_overrides)
        init_budget_event = PlannerBudgetInitializer.register_and_emit_init(
            planner_registry=planner_registry,
            orchestrator_id=effective_orchestrator_id,
            run_id=str(run_id),
            planner_limits=planner_limits,
        )
        if init_budget_event is not None:
            yield init_budget_event

        while runtime_state.iter_count < self._max_iterations:
            planner_iteration = runtime_state.iter_count + 1
            planner_iteration_id = f"{planner_run_id}:planner:{planner_iteration}"
            planner_event_ctx = {
                "planner_run_id": planner_run_id,
                "planner_iteration_id": planner_iteration_id,
                "iteration": planner_iteration,
            }
            iteration_context_snapshot = compact_snapshot(
                inputs={
                    "goal": runtime_state.goal or request.request_text,
                    "current_user_query": runtime_state.current_user_query,
                    "iteration_intent": f"Choose next step for iteration #{planner_iteration}",
                },
                limits=serialize_limits(planner_limits),
                meta={
                    "attempt": planner_iteration,
                    "max_attempts": self._max_iterations,
                    "available_agents": [
                        str(agent.get("slug") or "")
                        for agent in planner_agents
                        if str(agent.get("slug") or "").strip()
                    ],
                    "memory_digest": {
                        "facts": len(runtime_state.runtime_facts),
                        "summary_chars": len(str(runtime_state.memory_bundle.compact_view())),
                    },
                    "continuation": dict(runtime_state.continuation or {}) or None,
                },
            )
            yield PhasedEvent(
                RuntimeEvent.planner_iteration_start(
                    iteration_id=planner_iteration_id,
                    orchestrator_id=effective_orchestrator_id,
                    iteration=planner_iteration,
                    context_snapshot=iteration_context_snapshot,
                ),
                OrchestrationPhase.PLANNER,
            )
            step_budget = PlannerBudgetGuard.consume_step(
                planner_registry=planner_registry,
                orchestrator_id=effective_orchestrator_id,
                run_id=str(run_id),
            )
            if not step_budget.ok:
                runtime_state.status = PipelineStopReason.FAILED.value
                runtime_state.final_error = step_budget.final_error
                if step_budget.error_event is not None:
                    yield step_budget.error_event
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
                    error_message=step_budget.error_message,
                )
                return
            if step_budget.snapshot_event is not None:
                yield step_budget.snapshot_event

            try:
                if getattr(runtime_state, "execution_mode", ExecutionMode.NORMAL) == ExecutionMode.THINKING:
                    yield PhasedEvent(
                        RuntimeEvent.status(
                            "planner_thinking",
                            execution_mode=ExecutionMode.THINKING.value,
                            planner_run_id=planner_run_id,
                            planner_iteration_id=planner_iteration_id,
                            iteration=planner_iteration,
                        ),
                        OrchestrationPhase.PLANNER,
                    )
                step, planner_llm_traces = await PlannerNextStepInvoker.invoke(
                    planner=self._planner,
                    runtime_state=runtime_state,
                    available_agents=planner_agents,
                    outline=runtime_state.outline,
                    platform_config=platform_config,
                    chat_id=chat_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_run_id=run_id,
                    planner_iteration_id=planner_event_ctx["planner_iteration_id"],
                    sandbox_overrides=request.sandbox_overrides,
                )
                if not isinstance(step, NextStep):
                    # Fallback for malformed planner output not validated by the planner service.
                    raise TypeError(f"planner returned invalid step object: {type(step)!r}")
            except Exception as exc:
                logger.error(
                    "Planner failure on iter=%s: %s", runtime_state.iter_count, exc, exc_info=True
                )
                failure = PlannerFailureHandler.from_exception(
                    exc=exc,
                    planner_iteration_id=planner_iteration_id,
                    orchestrator_id=effective_orchestrator_id,
                    planner_iteration=planner_iteration,
                )
                runtime_state.status = PipelineStopReason.FAILED.value
                runtime_state.final_error = failure.final_error
                yield failure.error_event
                yield failure.iteration_end_event
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.FAILED,
                    stop_reason=PipelineStopReason.FAILED,
                    error_message=failure.error_message,
                )
                return

            runtime_state.iter_count = planner_iteration

            for planner_llm_trace in planner_llm_traces:
                yield PlannerLLMTraceEmitter.emit_turn_event(
                    planner_llm_trace=planner_llm_trace,
                    planner_iteration_id=planner_event_ctx["planner_iteration_id"],
                    planner_run_id=planner_event_ctx["planner_run_id"],
                )
                if (
                    str(getattr(planner_llm_trace, "step_kind", "")) == "thinking"
                    and bool(getattr(planner_llm_trace, "success", False))
                    and isinstance(getattr(planner_llm_trace, "parsed_response", None), dict)
                ):
                    yield PlannerStepEmitter.persist_and_emit_thinking(
                        runtime_state=runtime_state,
                        planner_iteration=planner_iteration,
                        planner_iteration_id=planner_iteration_id,
                        planner_run_id=planner_run_id,
                        thinking_payload=dict(planner_llm_trace.parsed_response),
                    )
                if not bool(getattr(planner_llm_trace, "success", True)):
                    yield PhasedEvent(
                        RuntimeEvent(
                            RuntimeEventType.PROTOCOL_RETRY,
                            {
                                "planner_run_id": planner_run_id,
                                "planner_iteration_id": planner_iteration_id,
                                "attempt": int(getattr(planner_llm_trace, "attempt", 0) or 0),
                                "reason": str(getattr(planner_llm_trace, "retry_reason", "") or "planner_retry"),
                            },
                        ),
                        OrchestrationPhase.PLANNER,
                    )
                llm_budget = PlannerBudgetGuard.consume_planner_llm_trace(
                    planner_registry=planner_registry,
                    orchestrator_id=effective_orchestrator_id,
                    run_id=str(run_id),
                    llm_trace=planner_llm_trace,
                )
                if not llm_budget.ok:
                    runtime_state.status = PipelineStopReason.FAILED.value
                    runtime_state.final_error = llm_budget.final_error
                    if llm_budget.error_event is not None:
                        yield llm_budget.error_event
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
                        error_message=llm_budget.error_message,
                    )
                    return
                if llm_budget.snapshot_event is not None:
                    yield llm_budget.snapshot_event

            yield PlannerStepEmitter.persist_and_emit(
                runtime_state=runtime_state,
                step=step,
                planner_iteration=planner_iteration,
                planner_iteration_id=planner_iteration_id,
                planner_run_id=planner_run_id,
            )

            # Loop detection is driven by sub-agent action signatures, not
            # planner records — check after agent execution below.

            # --- Dispatch -------------------------------------------------
            terminal_events, terminal_result = PlannerStepDispatcher.dispatch_terminal_step(
                step=step,
                runtime_state=runtime_state,
                run_id=str(run_id),
                planner_iteration=planner_iteration,
                planner_iteration_id=planner_iteration_id,
                orchestrator_id=effective_orchestrator_id,
            )
            for terminal_event in terminal_events:
                yield terminal_event
            if terminal_result is not None:
                mapped = PlanningOutcomeMapper.from_terminal_result(terminal_result)
                terminal_kind_name = PlanningOutcomeMapper.TERMINAL_KIND_MAP.get(
                    mapped["outcome_kind"],
                    "FAILED",
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind[terminal_kind_name],
                    stop_reason=mapped.get("stop_reason") or PipelineStopReason.FAILED,
                    answer_brief=mapped.get("answer_brief"),
                    final_answer_strategy=mapped.get("final_answer_strategy", "synthesize"),
                    error_message=mapped.get("error_message"),
                )
                return

            # kind == CALL_AGENT
            call_agent_dispatcher = PlannerCallAgentDispatcher(agent_executor=self._agent)
            async for event in call_agent_dispatcher.run(
                step=step,
                runtime_state=runtime_state,
                request=request,
                ctx=ctx,
                user_id=user_id,
                tenant_id=tenant_id,
                platform_config=platform_config,
                planner_agents=planner_agents,
                run_id=str(run_id),
                planner_iteration=planner_iteration,
                planner_iteration_id=planner_iteration_id,
                effective_orchestrator_id=effective_orchestrator_id,
                agent_version_id=self._resolve_agent_version_override(request),
            ):
                yield event

            dispatch_result = call_agent_dispatcher.result
            mapped_dispatch = (
                PlanningOutcomeMapper.from_call_agent_result(dispatch_result)
                if dispatch_result is not None
                else None
            )
            if mapped_dispatch is not None:
                call_kind_name = PlanningOutcomeMapper.CALL_AGENT_KIND_MAP.get(
                    mapped_dispatch["outcome_kind"],
                    "FAILED",
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind[call_kind_name],
                    stop_reason=mapped_dispatch.get("stop_reason") or PipelineStopReason.FAILED,
                    answer_brief=mapped_dispatch.get("answer_brief"),
                )
                return

            arbiter_events, arbiter_result = PlannerPostCallArbiter.evaluate(
                runtime_state=runtime_state,
                planner_run_id=planner_run_id,
                planner_iteration_id=planner_iteration_id,
                planner_iteration=planner_iteration,
                orchestrator_id=effective_orchestrator_id,
                loop_threshold=self._resolve_loop_threshold(request, platform_config),
            )
            for event in arbiter_events:
                yield event
            if arbiter_result.should_stop:
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.NEEDS_FINAL,
                    stop_reason=arbiter_result.stop_reason or PipelineStopReason.LOOP_DETECTED,
                    answer_brief=None,
                )
                return

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
            answer_brief=None,
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
    def _resolve_loop_threshold(request: PipelineRequest, platform_config: Dict[str, Any]) -> int:
        raw = (
            (request.sandbox_overrides or {})
            .get("runtime_budget", {})
            .get("loop_threshold")
        )
        if raw is None and isinstance(platform_config, dict):
            raw = (
                platform_config.get("runtime_budget", {}) if isinstance(platform_config.get("runtime_budget"), dict) else {}
            ).get("loop_threshold")
        if raw is None and isinstance(platform_config, dict):
            raw = platform_config.get("budget_loop_threshold")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return 3
        return max(1, value)
