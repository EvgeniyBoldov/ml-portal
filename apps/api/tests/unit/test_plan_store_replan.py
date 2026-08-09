from __future__ import annotations

import pytest

from app.runtime.orchestrator_contracts import (
    AgentTaskResult,
    NeedSpec,
    PlanPatch,
    PlannedTask,
    PlannerDecisionKind,
    TaskOutputSpec,
    TaskOutcome,
)
from app.runtime.plan_store import InMemoryPlanStore, PlanValidationError


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


def test_required_need_blocks_task_until_provider_output_resolves_it() -> None:
    store = InMemoryPlanStore()
    plan = store.create(goal="report", root_run_id="run", tenant_id="tenant")
    provider = PlannedTask(
        task_id="provider",
        executor="viewer",
        intent="find data",
        instructions="Find data",
        expected_outputs=[TaskOutputSpec(key="policy", description="Policy text")],
    )
    consumer = PlannedTask(
        task_id="consumer",
        executor="technical_writer",
        intent="write report",
        instructions="Write report",
        depends_on=["provider"],
        needs=[NeedSpec(key="policy", description="Required policy")],
    )
    store.apply_patch(
        plan["id"],
        PlanPatch(expected_revision=0, decision=PlannerDecisionKind.CREATE_PLAN, tasks=[provider, consumer]),
    )
    claimed = store.claim_ready(plan["id"])
    assert claimed is not None and claimed["task_id"] == "provider"
    with pytest.raises(PlanValidationError, match="missing required outputs"):
        store.apply_result(
            plan["id"],
            "provider",
            AgentTaskResult(outcome=TaskOutcome.COMPLETED, summary="done"),
        )
    store.apply_result(
        plan["id"],
        "provider",
        AgentTaskResult(
            outcome=TaskOutcome.COMPLETED,
            summary="done",
            outputs={"policy": "approved policy"},
        ),
    )
    claimed = store.claim_ready(plan["id"])
    assert claimed is not None and claimed["task_id"] == "consumer"


def test_user_resolves_waiting_need_and_reactivates_only_its_task() -> None:
    store = InMemoryPlanStore()
    plan = store.create(goal="decision", root_run_id="run", tenant_id="tenant")
    task = PlannedTask(
        task_id="decision",
        executor="viewer",
        intent="ask",
        instructions="Need a decision",
        needs=[NeedSpec(key="choice", kind="decision", description="User choice")],
    )
    store.apply_patch(
        plan["id"],
        PlanPatch(expected_revision=0, decision=PlannerDecisionKind.CREATE_PLAN, tasks=[task]),
    )
    store.apply_patch(
        plan["id"],
        PlanPatch(expected_revision=1, decision=PlannerDecisionKind.ASK_USER, question="Choose"),
    )
    assert store.resolve_waiting_need(plan["id"], user_input="approved") == "choice"
    claimed = store.claim_ready(plan["id"])
    assert claimed is not None and claimed["task_id"] == "decision"
