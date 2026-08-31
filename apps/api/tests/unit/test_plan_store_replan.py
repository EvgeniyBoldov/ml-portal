from __future__ import annotations

import pytest

from app.runtime.orchestrator_contracts import (
    NeedSpec,
    PlanPatch,
    PlannedTask,
    PlannerDecisionKind,
    TaskOutputSpec,
    TaskOutputValue,
    TaskOutcome,
    TaskResult,
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
        TaskResult(outcome=TaskOutcome.UNFULFILLABLE, summary="tool backend unavailable"),
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
            TaskResult(outcome=TaskOutcome.COMPLETED, summary="done"),
        )
    store.apply_result(
        plan["id"],
        "provider",
        TaskResult(
            outcome=TaskOutcome.COMPLETED,
            summary="done",
            outputs={"policy": TaskOutputValue(text="approved policy")},
        ),
    )
    claimed = store.claim_ready(plan["id"])
    assert claimed is not None and claimed["task_id"] == "consumer"


def test_task_result_without_required_output_does_not_complete_task() -> None:
    store = InMemoryPlanStore()
    plan = store.create(goal="fresh report", root_run_id="run", tenant_id="tenant")
    task = PlannedTask(
        task_id="retrieve",
        executor="viewer",
        intent="Retrieve current policy",
        instructions="Retrieve it",
        freshness_policy="require_retrieval",
        expected_outputs=[TaskOutputSpec(key="policy", description="Current policy")],
    )
    store.apply_patch(
        plan["id"],
        PlanPatch(expected_revision=0, decision=PlannerDecisionKind.CREATE_PLAN, tasks=[task]),
    )
    assert store.claim_ready(plan["id"])
    with pytest.raises(PlanValidationError, match="missing required outputs"):
        store.apply_result(
            plan["id"],
            "retrieve",
            TaskResult(
                outcome=TaskOutcome.COMPLETED,
                summary="invented",
            ),
        )


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


def test_planner_checkpoint_completes_and_extends_the_graph() -> None:
    store = InMemoryPlanStore()
    plan = store.create(goal="tickets", root_run_id="run", tenant_id="tenant")
    discover = PlannedTask(
        task_id="discover",
        executor="jira",
        intent="Find tickets",
        instructions="Return tickets",
    )
    checkpoint = PlannedTask(
        task_id="after_discovery",
        kind="planner",
        intent="Assess tickets",
        instructions="Build the next graph segment",
        depends_on=["discover"],
    )
    store.apply_patch(
        plan["id"],
        PlanPatch(expected_revision=0, decision=PlannerDecisionKind.CREATE_PLAN, tasks=[discover, checkpoint]),
    )
    assert store.claim_ready(plan["id"])["task_id"] == "discover"
    store.apply_result(
        plan["id"],
        "discover",
        TaskResult(
            outcome=TaskOutcome.COMPLETED,
            summary="found",
            outputs={"tickets": TaskOutputValue(data=[{"key": "OPS-1"}])},
        ),
    )
    claimed = store.claim_ready(plan["id"])
    assert claimed is not None and claimed["task_id"] == "after_discovery"

    follow_up = PlannedTask(
        task_id="prioritize",
        executor="analyst",
        intent="Prioritize tickets",
        instructions="Rank discovered tickets",
    )
    store.complete_planner_checkpoint(
        plan["id"],
        "after_discovery",
        PlanPatch(expected_revision=1, tasks=[follow_up]),
    )

    assert store.get(plan["id"])["tasks"]["after_discovery"]["status"] == "completed"
    assert store.claim_ready(plan["id"])["task_id"] == "prioritize"


def test_confirmation_resume_reactivates_only_bound_task() -> None:
    store = InMemoryPlanStore()
    plan = store.create(goal="change", root_run_id="run", tenant_id="tenant")
    confirmed = PlannedTask(
        task_id="apply_change",
        executor="operator",
        intent="Apply change",
        instructions="Apply the approved change",
    )
    unrelated = PlannedTask(
        task_id="follow_up",
        executor="operator",
        intent="Follow up",
        instructions="Run only after the change",
        depends_on=["apply_change"],
    )
    store.apply_patch(
        plan["id"],
        PlanPatch(expected_revision=0, decision=PlannerDecisionKind.CREATE_PLAN, tasks=[confirmed, unrelated]),
    )
    assert store.claim_ready(plan["id"])["task_id"] == "apply_change"
    task = store.get(plan["id"])["tasks"]["apply_change"]
    task["status"] = "waiting_user"
    task["checkpoint"] = {"confirmation": {"operation_fingerprint": "operation-1"}}
    store.get(plan["id"])["status"] = "waiting_input"

    with pytest.raises(PlanValidationError, match="fingerprint"):
        store.resume_confirmation_task(plan["id"], "apply_change", operation_fingerprint="other")

    resumed = store.resume_confirmation_task(
        plan["id"],
        "apply_change",
        operation_fingerprint="operation-1",
    )

    assert resumed["status"] == "ready"
    assert store.get(plan["id"])["tasks"]["follow_up"]["status"] == "pending"
