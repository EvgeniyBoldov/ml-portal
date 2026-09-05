"""Persisted graph planning stage used by the RuntimePipeline."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import UUID

from app.agents.context import ToolContext
from app.runtime.contracts import PipelineRequest, PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType
from app.runtime.orchestrator import GraphOrchestrator
from app.runtime.plan_store import SqlPlanStore
from app.runtime.turn_state import RuntimeTurnState
from app.runtime.memory.service import MemorySnapshot
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService


class GraphPlanningOutcomeKind(str, Enum):
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"


@dataclass
class GraphPlanningOutcome:
    kind: GraphPlanningOutcomeKind
    stop_reason: PipelineStopReason
    pause_question: Optional[str] = None
    pause_message: Optional[str] = None
    pause_context: Optional[Dict[str, Any]] = None


class GraphPlanningStage:
    """Create/resume a persisted plan and stream its deterministic execution."""

    def __init__(self, *, orchestrator: GraphOrchestrator, store: SqlPlanStore, max_steps: int) -> None:
        self._orchestrator = orchestrator
        self._store = store
        self._max_steps = max_steps
        self.outcome: Optional[GraphPlanningOutcome] = None

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
        planner_rbac_audit: Optional[Dict[str, Any]] = None,
        planner_memory_context: Optional[List[Dict[str, Any]]] = None,
        durable_memory_snapshot: Optional[MemorySnapshot] = None,
        orchestrator_id: Optional[str] = None,
        runtime_limits: Optional[Dict[str, int]] = None,
    ) -> AsyncIterator[PhasedEvent]:
        pause_question: Optional[str] = None
        pause_message: Optional[str] = None
        confirmation_context: Optional[Dict[str, Any]] = None
        runtime_sink = ctx.extra.get("runtime_event_logger") if isinstance(ctx.extra, dict) else None
        if runtime_sink is not None:
            async def emit_planner_event(event: RuntimeEvent) -> None:
                nonlocal pause_question
                if event.type == RuntimeEventType.WAITING_INPUT:
                    pause_question = str(event.data.get("question") or "").strip() or None
                await runtime_sink.emit(event, phase=OrchestrationPhase.PLANNER)

            self._orchestrator.event_sink = emit_planner_event
            if self._orchestrator.budget_service is not None:
                self._orchestrator.budget_service.event_sink = emit_planner_event
        run_id = UUID(str(runtime_state.run_id))
        plan = await self._store.get_by_run(run_id)
        if plan is None:
            plan = await self._store.create(
                goal=runtime_state.goal,
                root_run_id=run_id,
                tenant_id=tenant_id,
                chat_id=UUID(request.chat_id) if request.chat_id else None,
            )
        resume_action = str((runtime_state.continuation or {}).get("resume_action") or "").strip().lower()
        resume_user_response: Optional[str] = None
        if plan.status == "waiting_input":
            if resume_action == "confirm":
                paused_action = (
                    runtime_state.continuation.get("paused_action")
                    if isinstance(runtime_state.continuation, dict) and isinstance(runtime_state.continuation.get("paused_action"), dict)
                    else {}
                )
                paused_context = (
                    runtime_state.continuation.get("paused_context")
                    if isinstance(runtime_state.continuation, dict) and isinstance(runtime_state.continuation.get("paused_context"), dict)
                    else {}
                )
                confirmation_task_id = str(
                    paused_context.get("task_id") or paused_action.get("task_id") or ""
                ).strip()
                if not confirmation_task_id:
                    raise ValueError("confirmation resume is missing task_id")
                operation_fingerprint = RuntimeHitlProtocolService.extract_operation_fingerprint(
                    paused_action,
                    paused_context,
                )
                if not operation_fingerprint:
                    raise ValueError("confirmation resume is missing operation_fingerprint")
                await self._store.resume_confirmation_task(
                    plan.id,
                    confirmation_task_id,
                    operation_fingerprint=operation_fingerprint,
                )
            else:
                # request_text is the original chat content on a continuation;
                # RuntimeTurnState holds the actual answer from the checkpoint.
                resume_user_response = str(runtime_state.current_user_query or "").strip()
                await self._store.resolve_waiting_need(plan.id, user_input=resume_user_response)
                await self._store.resume_planner_pause(plan.id)
        effective_runtime_limits = dict(runtime_limits or {})
        task_attempts_limit = effective_runtime_limits.get("task_attempts")
        if isinstance(task_attempts_limit, int) and task_attempts_limit > 0:
            self._orchestrator.max_attempts = task_attempts_limit
        planner_kwargs = {
            "chat_id": UUID(request.chat_id) if request.chat_id else None,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "agent_execution_id": run_id,
            "sandbox_overrides": request.sandbox_overrides,
            "runtime_state": runtime_state,
            "messages": request.messages,
            "ctx": ctx,
            "platform_config": platform_config,
            "model": request.model,
            "planner_rbac_audit": dict(planner_rbac_audit or {}),
            "planner_memory_context": list(planner_memory_context or []),
            "durable_memory_snapshot": durable_memory_snapshot,
            "force_replan": resume_user_response is not None,
            "resume_user_response": resume_user_response,
            "runtime_limits": effective_runtime_limits,
            "budget_registry": ctx.extra.get("runtime_budget_registry"),
            "budget_resolver": ctx.extra.get("runtime_budget_resolver"),
        }
        async for event in self._orchestrator.run(
            plan_id=plan.id,
            goal=plan.goal,
            available_agents=available_agents,
            available_artifacts=[
                item.model_dump(mode="json")
                for item in runtime_state.attachment_contexts
                if item.ref.artifact_id not in runtime_state.deleted_artifact_ids
            ],
            max_steps=self._max_steps,
            planner_kwargs=planner_kwargs,
        ):
            runtime_event = event.to_runtime_event()
            if runtime_event.type == RuntimeEventType.WAITING_INPUT:
                pause_question = str(runtime_event.data.get("question") or "").strip() or None
            elif runtime_event.type == RuntimeEventType.CONFIRMATION_REQUIRED:
                pause_message = str(
                    runtime_event.data.get("message") or runtime_event.data.get("summary") or ""
                ).strip() or None
                confirmation_context = dict(runtime_event.data or {})
            phase = event.get("phase")
            try:
                event_phase = OrchestrationPhase(str(phase)) if phase else OrchestrationPhase.PLANNER
            except ValueError:
                event_phase = OrchestrationPhase.PLANNER
            yield PhasedEvent(runtime_event, event_phase)
        snapshot = await self._store.snapshot(plan.id)
        status = str(snapshot["status"])
        if status == "completed":
            self.outcome = GraphPlanningOutcome(
                kind=GraphPlanningOutcomeKind.COMPLETED,
                stop_reason=PipelineStopReason.COMPLETED,
            )
        elif status == "waiting_input":
            is_confirmation = confirmation_context is not None
            self.outcome = GraphPlanningOutcome(
                kind=GraphPlanningOutcomeKind.PAUSED,
                stop_reason=(PipelineStopReason.WAITING_CONFIRMATION if is_confirmation else PipelineStopReason.WAITING_INPUT),
                pause_question=pause_question,
                pause_message=pause_message,
                pause_context=confirmation_context,
            )
        else:
            self.outcome = GraphPlanningOutcome(
                kind=GraphPlanningOutcomeKind.FAILED,
                stop_reason=PipelineStopReason.FAILED,
            )
