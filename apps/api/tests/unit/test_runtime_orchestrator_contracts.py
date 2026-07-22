from datetime import datetime, timezone

import pytest

from app.runtime.orchestrator_contracts import (
    AgentTaskResult,
    PlanPatch,
    PlanRequest,
    TaskAttemptFailure,
    TaskOutcome,
    RequirementSpec,
    parse_agent_task_result,
    PlannerDecisionKind,
)
from app.runtime.plan_store import InMemoryPlanStore, PlanConflictError, PlanValidationError
from app.runtime.planner.simple_planner import SimplePlanner


def test_agent_result_distinguishes_business_outcome_from_technical_failure():
    result = AgentTaskResult(
        outcome=TaskOutcome.UNFULFILLABLE,
        reason_code="access_denied",
        summary="The source is not available",
    )
    failure = TaskAttemptFailure(code="provider_timeout", message="upstream timeout", retryable=True)
    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert failure.retryable is True


def test_result_requires_needs_for_dependency_pause():
    with pytest.raises(ValueError, match="requires at least one need"):
        AgentTaskResult(outcome=TaskOutcome.NEEDS_DEPENDENCY)


def test_agent_result_parser_rejects_prose_and_markdown_fences():
    with pytest.raises(ValueError, match="strict JSON"):
        parse_agent_task_result("Here is the result: {\"outcome\": \"completed\"}")
    with pytest.raises(ValueError, match="strict JSON"):
        parse_agent_task_result("```json\n{\"outcome\": \"completed\"}\n```")

    result = parse_agent_task_result('{"outcome":"completed","outputs":{"value":1}}')
    assert result.outputs["value"] == 1


def test_store_rejects_revision_conflict_and_cycles():
    store = InMemoryPlanStore()
    plan = store.create(goal="goal", root_run_id="run", tenant_id="tenant")
    patch = PlanPatch(expected_revision=0, tasks=[])
    store.apply_patch(plan["id"], patch)
    with pytest.raises(PlanConflictError):
        store.apply_patch(plan["id"], PlanPatch(expected_revision=0))

    cycle = PlanPatch(
        expected_revision=1,
        tasks=[
            {"task_id": "a", "title": "A", "objective": "A", "agent_slug": "a", "depends_on": ["b"]},
            {"task_id": "b", "title": "B", "objective": "B", "agent_slug": "b", "depends_on": ["a"]},
        ],
    )
    with pytest.raises(PlanValidationError, match="cycle"):
        store.apply_patch(plan["id"], cycle)


def test_simple_planner_creates_initial_task_from_short_catalogue():
    plan = InMemoryPlanStore().create(goal="find answer", root_run_id="run", tenant_id="tenant")
    patch = SimplePlanner().create_or_revise(
        request=PlanRequest(
            goal="find answer",
            plan=plan,
            available_agents=[{"slug": "general", "description": "short"}],
        )
    )
    assert patch.tasks[0].agent_slug == "general"
    assert patch.tasks[0].objective == "find answer"


def test_terminal_planner_decisions_require_context():
    with pytest.raises(ValueError, match="ask_user requires"):
        PlanPatch(expected_revision=0, decision=PlannerDecisionKind.ASK_USER)
    with pytest.raises(ValueError, match="fail_plan requires"):
        PlanPatch(expected_revision=0, decision=PlannerDecisionKind.FAIL_PLAN)
