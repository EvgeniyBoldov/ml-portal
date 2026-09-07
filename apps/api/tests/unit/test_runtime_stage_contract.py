from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.runtime.orchestrator_contracts import (
    IterationProposal, ResolutionAction, SchedulerActionKind, SynthesisBrief,
    TaskAttemptFailure, TaskResolution, TaskStatus, TerminalKind, PlannedTask,
)
from app.runtime.plan_store import InMemoryPlanStore


def _task(task_id: str, *, depends_on: list[str] | None = None) -> PlannedTask:
    return PlannedTask(task_id=task_id, executor="research", intent=task_id, instructions=task_id, depends_on=depends_on or [])


def _brief() -> SynthesisBrief:
    return SynthesisBrief(user_question="q", planned_work="work", purpose="purpose", answer_requirements="answer")


def test_synthesis_requires_brief_and_tasks_cannot_be_checkpoints() -> None:
    with pytest.raises(ValueError, match="synthesis_brief"):
        IterationProposal(tasks=[], terminal=TerminalKind.SYNTHESIS)
    with pytest.raises(ValueError, match="extra"):
        PlannedTask(task_id="work", executor="research", intent="work", instructions="work", kind="synthesis")


def test_failed_synthesis_iteration_deterministically_returns_to_planner() -> None:
    store = InMemoryPlanStore()
    plan = store.create(goal="g", root_run_id="run", tenant_id="tenant")
    store.apply_iteration(plan["id"], IterationProposal(tasks=[_task("work")], terminal=TerminalKind.SYNTHESIS, synthesis_brief=_brief()))
    task = store.claim_task(plan["id"], "work")
    store.finish_failure(plan["id"], task["task_id"], failure=TaskAttemptFailure(code="denied", message="Denied"), max_attempts=1)
    decision = store.next_decision(plan["id"])
    assert decision.kind is SchedulerActionKind.INVOKE_PLANNER
    assert decision.reason == "task_failure"


def test_independent_work_finishes_before_planner_checkpoint() -> None:
    store = InMemoryPlanStore()
    plan = store.create(goal="g", root_run_id="run", tenant_id="tenant")
    store.apply_iteration(plan["id"], IterationProposal(tasks=[_task("failed"), _task("independent"), _task("dependent", depends_on=["failed"])], terminal=TerminalKind.SYNTHESIS, synthesis_brief=_brief()))
    first = store.claim_task(plan["id"], "failed")
    store.finish_failure(plan["id"], first["task_id"], failure=TaskAttemptFailure(code="denied", message="Denied"), max_attempts=1)
    assert store.next_decision(plan["id"]).task_id == "independent"
    assert store.get(plan["id"])["tasks"]["dependent"]["status"] == TaskStatus.BLOCKED.value


def test_partial_output_requires_explicit_resolution() -> None:
    with pytest.raises(ValueError, match="output_keys"):
        TaskResolution(task_id="old", action=ResolutionAction.ACCEPT_PARTIAL, reason="usable")
    with pytest.raises(ValueError, match="replacement_task_ids"):
        TaskResolution(task_id="old", action=ResolutionAction.CONTINUE_WITH_TASKS, reason="retry")


def test_rejected_confirmation_is_a_task_failure_for_planner() -> None:
    store = InMemoryPlanStore()
    plan = store.create(goal="g", root_run_id="run", tenant_id="tenant")
    store.apply_iteration(plan["id"], IterationProposal(tasks=[_task("write")], terminal=TerminalKind.PLANNER))
    store.claim_task(plan["id"], "write")
    store.pause_confirmation(plan["id"], "write", {"operation_fingerprint": "op-1"})
    store.reject_confirmation(plan["id"], "write", "op-1")
    assert store.next_decision(plan["id"]).kind is SchedulerActionKind.INVOKE_PLANNER


def test_stale_task_claim_is_recovered_without_reusing_the_attempt() -> None:
    store = InMemoryPlanStore()
    plan = store.create(goal="g", root_run_id="run", tenant_id="tenant")
    store.apply_iteration(plan["id"], IterationProposal(tasks=[_task("work")], terminal=TerminalKind.PLANNER))
    store.claim_task(plan["id"], "work")
    plan["attempts"]["work"][-1]["started_at"] = (
        datetime.now(timezone.utc) - timedelta(minutes=10)
    ).isoformat()

    store.recover_stale_claims(
        plan["id"], stale_before=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    assert plan["tasks"]["work"]["status"] == TaskStatus.PENDING.value
    assert plan["attempts"]["work"][-1]["status"] == "failed"
    assert plan["attempts"]["work"][-1]["error"]["code"] == "claim_lease_expired"
