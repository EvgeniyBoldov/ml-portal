import pytest

from pydantic import ValidationError

from app.runtime.orchestrator_contracts import PlanPatch, PlannedTask, PlannerDecisionKind
from app.runtime.planner.graph_planner import PlannerGraphOutput


def test_graph_task_accepts_only_canonical_fields() -> None:
    payload = {
        "decision": "create_plan",
        "expected_revision": 0,
        "tasks": [
            {
                "task_id": "task-1",
                "intent": "Task",
                "instructions": "Do task",
                "executor": "viewer",
                "expected_outputs": [{"key": "answer", "description": "Answer"}],
                "needs": [{"key": "input", "description": "Input", "required": False}],
            }
        ],
    }

    patch = PlanPatch.model_validate(payload)

    assert patch.tasks[0].expected_outputs[0].key == "answer"
    assert patch.tasks[0].needs[0].required is False


def test_planner_output_preserves_enum_decision_for_plan_store() -> None:
    patch = PlannerGraphOutput.model_validate({
        "decision": "create_plan",
        "expected_revision": 0,
    })

    assert patch.decision is PlannerDecisionKind.CREATE_PLAN


def test_graph_task_rejects_removed_vocabulary() -> None:
    with pytest.raises(ValidationError):
        PlannedTask.model_validate({
            "task_id": "task-1",
            "title": "Prepare request",
            "objective": "Prepare request",
            "agent_slug": "viewer",
        })


def test_planner_output_rejects_create_plan_for_nonzero_revision() -> None:
    with pytest.raises(ValidationError, match="create_plan is valid only for revision zero"):
        PlannerGraphOutput.model_validate({
            "decision": "create_plan",
            "expected_revision": 1,
        })
