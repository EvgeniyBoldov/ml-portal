"""Persisted graph planning stage used by the RuntimePipeline."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import UUID

from app.agents.context import ToolContext
from app.runtime.contracts import PipelineRequest, PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.runtime.orchestrator import GraphOrchestrator
from app.runtime.plan_store import SqlPlanStore
from app.runtime.turn_state import RuntimeTurnState


class GraphPlanningOutcomeKind(str, Enum):
    NEEDS_FINAL = "needs_final"
    PAUSED = "paused"
    FAILED = "failed"


@dataclass
class GraphPlanningOutcome:
    kind: GraphPlanningOutcomeKind
    stop_reason: PipelineStopReason
    answer_brief: Optional[str] = None
    final_answer_strategy: str = "synthesize"


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
        orchestrator_id: Optional[str] = None,
    ) -> AsyncIterator[PhasedEvent]:
        runtime_sink = ctx.extra.get("runtime_event_logger") if isinstance(ctx.extra, dict) else None
        if runtime_sink is not None:
            async def emit_planner_event(event: RuntimeEvent) -> None:
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
        elif plan.status == "waiting_input":
            await self._store.resume_waiting_tasks(
                plan.id,
                user_input=str(request.request_text or "").strip(),
            )
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
        }
        async for event in self._orchestrator.run(
            plan_id=plan.id,
            goal=plan.goal,
            available_agents=available_agents,
            max_steps=self._max_steps,
            planner_kwargs=planner_kwargs,
        ):
            yield PhasedEvent(event.to_runtime_event(), OrchestrationPhase.PLANNER)
        snapshot = await self._store.snapshot(plan.id)
        status = str(snapshot["status"])
        if status == "completed":
            self.outcome = GraphPlanningOutcome(
                kind=GraphPlanningOutcomeKind.NEEDS_FINAL,
                stop_reason=PipelineStopReason.COMPLETED,
                answer_brief=None,
            )
        elif status == "waiting_input":
            self.outcome = GraphPlanningOutcome(
                kind=GraphPlanningOutcomeKind.PAUSED,
                stop_reason=PipelineStopReason.WAITING_INPUT,
            )
        else:
            self.outcome = GraphPlanningOutcome(
                kind=GraphPlanningOutcomeKind.FAILED,
                stop_reason=PipelineStopReason.FAILED,
            )
