import pytest

from pydantic import ValidationError

from app.runtime.orchestrator_contracts import PlanPatch, PlannedTask, PlannerDecisionKind
from app.runtime.planner.graph_planner import PlannerGraphOutput
from app.runtime.input_builders import PlannerInputBuilder


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
    output = PlannerGraphOutput.model_validate({
        "action": "apply_graph",
        # Stale custom prompts may still emit this runtime-owned field.  It
        # cannot override the snapshot revision selected by GraphPlanner.
        "expected_revision": 1,
    })
    patch = output.to_plan_patch(plan={"revision": 0, "tasks": {}})

    assert patch.decision is PlannerDecisionKind.CREATE_PLAN
    assert patch.expected_revision == 0


def test_planner_output_normalizes_legacy_decision_without_accepting_its_revision() -> None:
    output = PlannerGraphOutput.model_validate({
        "decision": "create_plan",
        "expected_revision": 99,
    })

    patch = output.to_plan_patch(plan={"revision": 0, "tasks": {}})

    assert patch.decision is PlannerDecisionKind.CREATE_PLAN
    assert patch.expected_revision == 0


def test_graph_task_rejects_removed_vocabulary() -> None:
    with pytest.raises(ValidationError):
        PlannedTask.model_validate({
            "task_id": "task-1",
            "title": "Prepare request",
            "objective": "Prepare request",
            "agent_slug": "viewer",
        })


def test_planner_output_uses_revise_for_existing_plan() -> None:
    output = PlannerGraphOutput.model_validate({"action": "apply_graph"})

    patch = output.to_plan_patch(plan={"revision": 3, "tasks": {}})

    assert patch.decision is PlannerDecisionKind.REVISE_PLAN
    assert patch.expected_revision == 3


def test_planner_output_rejects_terminal_task_mutation() -> None:
    with pytest.raises(ValidationError, match="complete cannot mutate tasks"):
        PlannerGraphOutput.model_validate({
            "action": "complete",
            "tasks": [{
                "task_id": "task-1",
                "intent": "Task",
                "instructions": "Do task",
                "executor": "viewer",
            }],
        })


def test_planner_input_hides_persistence_fields() -> None:
    payload = PlannerInputBuilder().build_graph_request(type("Request", (), {
        "goal": "Inspect sources",
        "trigger": "technical_failure",
        "plan": {
            "id": "plan-id",
            "root_run_id": "run-id",
            "tenant_id": "tenant-id",
            "revision": 4,
            "status": "active",
            "tasks": {"inspect": {"task_id": "inspect", "status": "completed"}},
        },
        "completed_outputs": {},
        "needs": [],
        "last_failure": None,
        "available_agents": [],
    })())

    assert payload["mode"] == "replan"
    assert payload["replan_reason"] == "technical_failure"
    assert payload["plan"] == {
        "has_existing_graph": True,
        "status": "active",
        "tasks": {"inspect": {"task_id": "inspect", "status": "completed"}},
    }
