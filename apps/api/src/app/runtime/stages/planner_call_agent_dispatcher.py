from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Literal, Optional
from uuid import uuid4

from app.agents.context import ToolContext
from app.core.db import get_session_factory
from app.runtime.contracts import NextStep, PipelineRequest, PipelineStopReason
from app.runtime.context_snapshot import compact_snapshot, prompt_snapshot, serialize_limits
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
from app.runtime.operation_errors import RuntimeErrorCode
from app.services.agent_service import AgentService
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
        agent_context_snapshot = await self._build_agent_context_snapshot(
            step=step,
            ctx=ctx,
            request=request,
            tenant_id=tenant_id,
            agent_version_id=agent_version_id,
        )
        agent_started = False

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
            if (
                event.type == RuntimeEventType.STATUS
                and str(event.data.get("stage") or "") == "agent_context_snapshot"
            ):
                merged_snapshot = self._merge_context_snapshots(
                    agent_context_snapshot,
                    event.data.get("context_snapshot"),
                )
                if merged_snapshot:
                    agent_context_snapshot = merged_snapshot
                continue

            if not agent_started:
                yield PhasedEvent(
                    RuntimeEvent.agent_start(
                        agent_run_id=lifecycle_agent_run_id,
                        parent_entity_id=planner_iteration_id,
                        parent_entity_type="planner_iteration",
                        agent_slug=step.agent_slug or "unknown",
                        context_snapshot=agent_context_snapshot,
                    ),
                    OrchestrationPhase.AGENT,
                )
                agent_started = True

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

        if not agent_started:
            yield PhasedEvent(
                RuntimeEvent.agent_start(
                    agent_run_id=lifecycle_agent_run_id,
                    parent_entity_id=planner_iteration_id,
                    parent_entity_type="planner_iteration",
                    agent_slug=step.agent_slug or "unknown",
                    context_snapshot=agent_context_snapshot,
                ),
                OrchestrationPhase.AGENT,
            )

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
                source="pipeline_internal",
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

    @staticmethod
    async def _build_agent_context_snapshot(
        *,
        step: NextStep,
        ctx: ToolContext,
        request: PipelineRequest,
        tenant_id: Any,
        agent_version_id: Any = None,
    ) -> Optional[Dict[str, Any]]:
        agent_slug = str(step.agent_slug or "").strip()
        if not agent_slug:
            return None

        prompt_text: Optional[str] = None
        model_name: Optional[str] = None
        version_label: Optional[str] = None
        runtime_deps = ctx.get_runtime_deps()
        session_factory = runtime_deps.session_factory or get_session_factory()
        try:
            async with session_factory() as session:
                service = AgentService(session)
                if agent_version_id:
                    version = await service.get_version(agent_version_id)
                else:
                    version = await service.resolve_published_version(agent_slug, tenant_id)
                prompt_text = getattr(version, "compiled_prompt", None)
                version_number = getattr(version, "version", None)
                version_status = getattr(version, "status", None)
                if version_number is not None:
                    version_label = f"v{version_number}"
                    if version_status:
                        version_label = f"{version_label} ({version_status})"
                agent = await service.get_agent(version.agent_id)
                model_name = getattr(agent, "model", None)
        except Exception:
            prompt_text = None
            model_name = None
            version_label = None

        agent_limits = None
        budget_resolver = ctx.extra.get("runtime_budget_resolver")
        try:
            if budget_resolver is not None:
                agent_limits = await budget_resolver.resolve_orchestrator(agent_slug, request.sandbox_overrides)
        except Exception:
            agent_limits = None

        return compact_snapshot(
            inputs={
                "agent_input": step.agent_input or {},
                "goal": request.request_text,
            },
            prompt=prompt_snapshot(prompt_text, str(ctx.extra.get("runtime_logging_level") or "brief")),
            limits=serialize_limits(agent_limits),
            meta={
                "role": agent_slug,
                "agent_slug": agent_slug,
                "model": model_name or request.model,
                "version_label": version_label,
            },
        )

    @staticmethod
    def _merge_context_snapshots(
        base: Optional[Dict[str, Any]],
        override: Any,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(base, dict):
            base = {}
        if not isinstance(override, dict):
            return base or None
        merged = deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = {**merged.get(key, {}), **value}
            else:
                merged[key] = value
        return merged or None
