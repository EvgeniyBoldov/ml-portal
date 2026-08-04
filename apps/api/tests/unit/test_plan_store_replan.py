from __future__ import annotations

from app.runtime.orchestrator_contracts import (
    AgentTaskResult,
    PlanPatch,
    PlannedTask,
    PlannerDecisionKind,
    TaskOutcome,
)
from app.runtime.plan_store import InMemoryPlanStore


def test_replan_reactivates_replaced_unfulfillable_task() -> None:
    store = InMemoryPlanStore()
    plan = store.create(goal="date", root_run_id="run", tenant_id="tenant")
    task = PlannedTask(
        task_id="get_date",
        executor="company_knowledge_agent",
        intent="get_today_date",
        instructions="Return today's date",
    )
    store.apply_patch(
        plan["id"],
        PlanPatch(expected_revision=0, decision=PlannerDecisionKind.CREATE_PLAN, tasks=[task]),
    )
    claimed = store.claim_ready(plan["id"])
    assert claimed is not None
    store.apply_result(
        plan["id"],
        "get_date",
        AgentTaskResult(outcome=TaskOutcome.UNFULFILLABLE, summary="tool backend unavailable"),
    )

    replacement = task.model_copy(update={"executor": "fallback_agent"})
    store.apply_patch(
        plan["id"],
        PlanPatch(expected_revision=1, tasks=[replacement]),
    )

    next_task = store.claim_ready(plan["id"])
    assert next_task is not None
    assert next_task["executor"] == "fallback_agent"
