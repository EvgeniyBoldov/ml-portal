from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Literal, Optional
from uuid import uuid4

from app.agents.context import ToolContext
from app.runtime.contracts import NextStep, PipelineRequest, PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
from app.runtime.operation_errors import RuntimeErrorCode
from app.runtime.planner.iteration_policy import (
    build_iteration_result,
    classify_agent_failure,
    latest_agent_result_payload,
)
from app.runtime.ports import AgentExecutionPort
from app.runtime.turn_state import RuntimeTurnState


@dataclass
class CallAgentDispatchResult:
    outcome: Literal["continue", "paused", "needs_final"]
    stop_reason: Optional[PipelineStopReason] = None


class PlannerCallAgentDispatcher:
    def __init__(self, *, agent_executor: AgentExecutionPort) -> None:
        self._agent = agent_executor
        self.result: Optional[CallAgentDispatchResult] = None

    async def run(
        self,
        *,
        step: NextStep,
        runtime_state: RuntimeTurnState,
        request: PipelineRequest,
        ctx: ToolContext,
        user_id: Any,
        tenant_id: Any,
        platform_config: Dict[str, Any],
        planner_agents: List[Dict[str, Any]],
        run_id: str,
        planner_iteration: int,
        planner_iteration_id: str,
        effective_orchestrator_id: str,
        agent_version_id: Any = None,
    ) -> AsyncIterator[PhasedEvent]:
        self.result = None
        agent_run_id = run_id
        lifecycle_agent_run_id = str(uuid4())
        yield PhasedEvent(
            RuntimeEvent.agent_start(
                agent_run_id=lifecycle_agent_run_id,
                parent_entity_id=planner_iteration_id,
                parent_entity_type="planner_iteration",
                agent_slug=step.agent_slug or "unknown",
            ),
            OrchestrationPhase.AGENT,
        )

        async for event in self._agent.execute(
            step=step,
            runtime_state=runtime_state,
            messages=request.messages,
            ctx=ctx,
            user_id=user_id,
            tenant_id=tenant_id,
            platform_config=platform_config,
            model=request.model,
            agent_version_id=agent_version_id,
            lifecycle_agent_run_id=lifecycle_agent_run_id,
        ):
            yield PhasedEvent(event, OrchestrationPhase.AGENT)
            if event.type == RuntimeEventType.CONFIRMATION_REQUIRED:
                runtime_state.status = PipelineStopReason.WAITING_CONFIRMATION.value
                message = str(event.data.get("summary") or event.data.get("message") or "").strip() or None
                stop_event_data: Dict[str, Any] = {
                    "reason": PipelineStopReason.WAITING_CONFIRMATION.value,
                    "run_id": run_id,
                }
                if message:
                    stop_event_data["message"] = message
                for key in ("operation_fingerprint", "tool_slug", "operation", "risk_level", "args_preview", "summary"):
                    val = event.data.get(key)
                    if val is not None:
                        stop_event_data[key] = val
                yield PhasedEvent(
                    RuntimeEvent(RuntimeEventType.STOP, stop_event_data),
                    OrchestrationPhase.PLANNER,
                )
                yield PhasedEvent(
                    RuntimeEvent.agent_end(
                        agent_run_id=lifecycle_agent_run_id,
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
                runtime_state.add_iteration_result(
                    build_iteration_result(
                        state=runtime_state,
                        iteration=planner_iteration,
                        step_kind=step.kind.value,
                        agent_slug=step.agent_slug,
                        phase_id=step.phase_id,
                        outcome="needs_confirmation",
                        summary=message or "",
                        sufficient_for_phase=False,
                    )
                )
                self.result = CallAgentDispatchResult(
                    outcome="paused",
                    stop_reason=PipelineStopReason.WAITING_CONFIRMATION,
                )
                return

        last_agent_result = latest_agent_result_payload(
            runtime_state,
            iteration=planner_iteration,
            agent_slug=step.agent_slug,
            phase_id=step.phase_id,
        )
        outcome = str(
            last_agent_result.get("outcome")
            or ("success" if bool(last_agent_result.get("success", False)) else "failed")
        )
        retryable = last_agent_result.get("retryable")
        error_code = str(last_agent_result.get("error_code") or "")
        agent_final_status = "completed" if outcome == "success" else "failed"

        failure_state = classify_agent_failure(runtime_state, agent_slug=step.agent_slug)
        # Prefer current-iteration payload over historical iteration_results.
        if outcome != "success":
            unavailable_codes = {
                RuntimeErrorCode.AGENT_PRECHECK_FAILED.value,
                RuntimeErrorCode.AGENT_UNAVAILABLE.value,
                RuntimeErrorCode.AGENT_NO_OPERATIONS.value,
            }
            non_retryable_codes = {
                RuntimeErrorCode.OPERATION_UNAVAILABLE.value,
                RuntimeErrorCode.OPERATION_AMBIGUOUS.value,
                RuntimeErrorCode.AGENT_NON_RETRYABLE_OPERATION_FAILURE.value,
                RuntimeErrorCode.AGENT_REQUIRED_OPERATION_CALL_MISSING.value,
                RuntimeErrorCode.AGENT_MAX_TOOL_CALLS_EXCEEDED.value,
                RuntimeErrorCode.AGENT_WALL_TIME_EXCEEDED.value,
            }
            failure_state["unavailable"] = error_code in unavailable_codes
            failure_state["non_retryable"] = bool(
                failure_state["unavailable"] or retryable is False or error_code in non_retryable_codes
            )

        if failure_state["unavailable"]:
            removed = self._remove_agent(planner_agents, step.agent_slug)
            if removed:
                yield PhasedEvent(
                    RuntimeEvent.status(
                        "planner_agent_removed_unavailable",
                        planner_run_id=agent_run_id,
                        planner_iteration_id=planner_iteration_id,
                        iteration=planner_iteration,
                        agent=step.agent_slug,
                        remaining_agents=len(planner_agents),
                    ),
                    OrchestrationPhase.PLANNER,
                )

        yield PhasedEvent(
            RuntimeEvent.agent_end(
                agent_run_id=lifecycle_agent_run_id,
                parent_entity_id=planner_iteration_id,
                parent_entity_type="planner_iteration",
                agent_slug=step.agent_slug or "unknown",
                status=agent_final_status,
            ),
            OrchestrationPhase.AGENT,
        )

        if failure_state["non_retryable"]:
            runtime_state.add_runtime_fact(
                "Agent failed with non-retryable runtime error; finalizing from collected facts.",
                source="pipeline",
            )
            yield PhasedEvent(
                RuntimeEvent.status(
                    "agent_non_retryable_failure_finalize",
                    planner_run_id=agent_run_id,
                    planner_iteration_id=planner_iteration_id,
                    iteration=planner_iteration,
                ),
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
            self.result = CallAgentDispatchResult(
                outcome="needs_final",
                stop_reason=PipelineStopReason.FAILED,
            )
            return

        runtime_state.add_iteration_result(
            build_iteration_result(
                state=runtime_state,
                iteration=planner_iteration,
                step_kind=step.kind.value,
                agent_slug=step.agent_slug,
                phase_id=step.phase_id,
                outcome=outcome,
                summary=str(last_agent_result.get("summary") or ""),
                missing_inputs=list(last_agent_result.get("missing_inputs") or []),
                sufficient_for_phase=bool(last_agent_result.get("sufficient_for_phase", False)),
                retryable=retryable,
                error_code=(error_code or None),
            )
        )
        self.result = CallAgentDispatchResult(outcome="continue")

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
