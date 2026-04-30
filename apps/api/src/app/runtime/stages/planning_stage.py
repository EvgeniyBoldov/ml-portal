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
from uuid import UUID

from app.agents.context import ToolContext
from app.core.logging import get_logger
from app.runtime.budget import RuntimeBudgetTracker
from app.runtime.contracts import (
    NextStepKind,
    PipelineRequest,
    PipelineStopReason,
)
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
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
        budget_tracker: Optional[RuntimeBudgetTracker] = None,
    ) -> None:
        self._planner = planner
        self._agent = agent_executor
        self._max_iterations = max_iterations
        self._budget_tracker = budget_tracker
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
    ) -> AsyncIterator[PhasedEvent]:
        run_id = runtime_state.run_id
        chat_id = runtime_state.chat_id
        runtime_state.goal = runtime_state.goal or request.request_text
        runtime_state.current_user_query = request.request_text
        planner_agents: List[Dict[str, Any]] = list(available_agents or [])

        while runtime_state.iter_count < self._max_iterations:
            if self._budget_tracker is not None and not self._budget_tracker.can_run_planner_iteration():
                break
            if self._budget_tracker is not None:
                self._budget_tracker.record_planner_iteration()
            yield PhasedEvent(
                RuntimeEvent.status(
                    "planner_thinking",
                    iteration=runtime_state.iter_count + 1,
                    budget=(
                        self._budget_tracker.snapshot()
                        if self._budget_tracker is not None
                        else None
                    ),
                ),
                OrchestrationPhase.PLANNER,
            )

            try:
                step = await self._planner.next_step(
                    runtime_state=runtime_state,
                    available_agents=planner_agents,
                    outline=runtime_state.outline,
                    platform_config=platform_config,
                    chat_id=chat_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    agent_run_id=run_id,
                )
            except Exception as exc:
                logger.error(
                    "Planner failure on iter=%s: %s", runtime_state.iter_count, exc, exc_info=True
                )
                runtime_state.status = PipelineStopReason.FAILED.value
                runtime_state.final_error = f"planner_exception: {exc}"
                yield PhasedEvent(
                    RuntimeEvent.error(f"Planner failed: {exc}", recoverable=False),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.FAILED,
                    stop_reason=PipelineStopReason.FAILED,
                    error_message=str(exc),
                )
                return

            step_record = {
                "iteration": runtime_state.iter_count + 1,
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
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.DIRECT,
                    stop_reason=PipelineStopReason.COMPLETED,
                    planner_hint=answer,
                )
                return

            if step.kind == NextStepKind.FINAL:
                runtime_state.status = PipelineStopReason.COMPLETED.value
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
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.PAUSED,
                    stop_reason=PipelineStopReason.WAITING_INPUT,
                )
                return

            if step.kind == NextStepKind.ABORT:
                runtime_state.status = PipelineStopReason.ABORTED.value
                runtime_state.final_error = step.rationale
                yield PhasedEvent(
                    RuntimeEvent.error(f"Aborted: {step.rationale}", recoverable=False),
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
            ):
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
                    self.outcome = PlanningOutcome(
                        kind=PlanningOutcomeKind.PAUSED,
                        stop_reason=PipelineStopReason.WAITING_CONFIRMATION,
                    )
                    return

            # Early degrade path: sub-agent failed with a known hard
            # token/payload limit error. Additional planner iterations usually
            # repeat the same failing call and add overhead.
            if self._last_agent_unavailable(runtime_state, step.agent_slug):
                removed = self._remove_agent(planner_agents, step.agent_slug)
                if removed:
                    yield PhasedEvent(
                        RuntimeEvent.status(
                            "planner_agent_removed_unavailable",
                            agent=step.agent_slug,
                            remaining_agents=len(planner_agents),
                        ),
                        OrchestrationPhase.PLANNER,
                    )
            if self._has_non_retryable_agent_failure(runtime_state, step.agent_slug):
                runtime_state.add_runtime_fact(
                    "Agent failed with non-retryable runtime error; finalizing from collected facts.",
                    source="pipeline",
                )
                yield PhasedEvent(
                    RuntimeEvent.status("agent_non_retryable_failure_finalize"),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.NEEDS_FINAL,
                    stop_reason=PipelineStopReason.FAILED,
                    planner_hint=None,
                )
                return

            loop_threshold = (
                self._budget_tracker.budget.loop_threshold
                if self._budget_tracker else 3
            )
            if runtime_state.detect_loop(threshold=loop_threshold):
                runtime_state.add_runtime_fact(
                    "Loop detected by runtime; synthesizing from facts.",
                    source="pipeline",
                )
                yield PhasedEvent(
                    RuntimeEvent.status("loop_detected"),
                    OrchestrationPhase.PLANNER,
                )
                self.outcome = PlanningOutcome(
                    kind=PlanningOutcomeKind.NEEDS_FINAL,
                    stop_reason=PipelineStopReason.LOOP_DETECTED,
                    planner_hint=None,
                )
                return

        # Max iterations reached → synthesize whatever we have.
        yield PhasedEvent(
            RuntimeEvent.status(
                "max_iters_reached",
                iterations=runtime_state.iter_count,
                budget=(
                    self._budget_tracker.snapshot()
                    if self._budget_tracker is not None
                    else None
                ),
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
