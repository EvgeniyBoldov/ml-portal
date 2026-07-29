import pytest
from pydantic import ValidationError

from app.runtime.orchestrator_contracts import PlanPatch
from app.runtime.plan_store import PlanValidationError, validate_task_graph


def task_payload(**overrides):
    return {
        "task_id": "task-1",
        "executor": "viewer",
        "intent": "Inspect",
        "instructions": "Inspect the result",
        **overrides,
    }


def test_patch_rejects_duplicate_dependencies_before_persistence():
    with pytest.raises(ValidationError, match="duplicate dependencies"):
        PlanPatch.model_validate({
            "expected_revision": 1,
            "decision": "revise_plan",
            "tasks": [task_payload(depends_on=["task-0", "task-0"])],
        })


def test_graph_validation_rejects_duplicate_dependencies_from_legacy_input():
    task = PlanPatch.model_validate({
        "expected_revision": 0,
        "decision": "create_plan",
        "tasks": [task_payload()],
    }).tasks[0].model_copy(update={"depends_on": ["task-1", "task-1"]})

    with pytest.raises(PlanValidationError, match="duplicate dependencies"):
        validate_task_graph([task])
