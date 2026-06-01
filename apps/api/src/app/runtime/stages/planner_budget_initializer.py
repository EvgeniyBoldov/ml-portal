from __future__ import annotations

from typing import Optional

from app.runtime.budgets import BudgetRegistry
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent


class PlannerBudgetInitializer:
    @staticmethod
    def register_and_emit_init(
        *,
        planner_registry: Optional[BudgetRegistry],
        orchestrator_id: str,
        run_id: str,
        planner_limits,
    ) -> Optional[PhasedEvent]:
        if planner_registry is None:
            return None
        planner_registry.register(
            entity_type="orchestrator",
            entity_id=orchestrator_id,
            parent_entity_id=run_id,
            role="planner",
            limits=planner_limits,
        )
        init_payload = planner_registry.emit_snapshot(orchestrator_id, reason="init") or {}
        return PhasedEvent(
            RuntimeEvent.budget_snapshot(
                entity_type="orchestrator",
                entity_id=orchestrator_id,
                parent_entity_type="run",
                parent_entity_id=run_id,
                role="planner",
                own=init_payload.get("own", {}),
                limits=init_payload.get("limits"),
                delta={},
                reason="init",
                at_ms=init_payload.get("at_ms"),
            ),
            OrchestrationPhase.PLANNER,
        )
