from app.runtime.orchestrator_contracts import PlanPatch
from app.runtime.planner.graph_planner import GraphPlanner


def test_normalise_patch_converts_weak_model_shorthands_to_plan_contract() -> None:
    payload = {
        "decision": "create_plan",
        "expected_revision": 0,
        "goal": "",
        "question": "",
        "tasks": [
            {
                "task_id": "connectivity",
                "title": "Prepare connectivity request",
                "objective": "Prepare the request data",
                "agent": "net.enginer",
                "expected_outputs": ["completed request"],
                "requirements": ["source and destination"],
            }
        ],
    }

    patch = PlanPatch.model_validate(GraphPlanner._normalise_patch(payload))

    assert patch.goal is None
    assert patch.question is None
    assert patch.tasks[0].agent_slug == "net.enginer"
    assert patch.tasks[0].expected_outputs[0].key == "output_1"
    assert patch.tasks[0].requirements[0].key == "source and destination"


def test_normalise_patch_keeps_canonical_nested_specs_unchanged() -> None:
    payload = {
        "decision": "create_plan",
        "expected_revision": 0,
        "tasks": [
            {
                "task_id": "task-1",
                "title": "Task",
                "objective": "Do task",
                "agent_slug": "viewer",
                "expected_outputs": [{"key": "answer", "description": "Answer"}],
                "requirements": [{"key": "input", "description": "Input", "required": False}],
            }
        ],
    }

    patch = PlanPatch.model_validate(GraphPlanner._normalise_patch(payload))

    assert patch.tasks[0].expected_outputs[0].key == "answer"
    assert patch.tasks[0].requirements[0].required is False


def test_normalise_patch_accepts_short_task_vocabulary() -> None:
    payload = {
        "decision": "create_plan",
        "expected_revision": 0,
        "tasks": [
            {
                "id": "task-1",
                "name": "Prepare request",
                "description": "Prepare the connectivity request",
                "agent_slug": "net.enginer",
                "dependencies": [],
                "outputs": ["request"],
            }
        ],
    }

    patch = PlanPatch.model_validate(GraphPlanner._normalise_patch(payload))

    assert patch.tasks[0].task_id == "task-1"
    assert patch.tasks[0].title == "Prepare request"
    assert patch.tasks[0].objective == "Prepare the connectivity request"
    assert patch.tasks[0].expected_outputs[0].description == "request"


def test_normalise_patch_converts_output_maps_to_specs() -> None:
    payload = {
        "decision": "create_plan",
        "expected_revision": 0,
        "tasks": [
            {
                "task_id": "task-1",
                "title": "Prepare request",
                "objective": "Prepare request",
                "agent_slug": "net.enginer",
                "expected_outputs": {"request_form": None},
                "requirements": {"source": None},
            }
        ],
    }

    patch = PlanPatch.model_validate(GraphPlanner._normalise_patch(payload))

    assert patch.tasks[0].expected_outputs[0].key == "request_form"
    assert patch.tasks[0].expected_outputs[0].description == "request_form"
    assert patch.tasks[0].requirements[0].key == "source"
