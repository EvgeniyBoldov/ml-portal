import pytest

from pydantic import ValidationError

from app.runtime.orchestrator_contracts import PlanNodeKind, PlanPatch, PlannedTask, PlannerDecisionKind
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
            },
            {
                "task_id": "synthesize",
                "kind": "synthesis",
                "intent": "Answer the user's request",
                "instructions": "Give a direct answer using the completed reports.",
            },
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


def test_planner_output_rejects_legacy_decision_shape() -> None:
    with pytest.raises(ValidationError):
        PlannerGraphOutput.model_validate({"decision": "create_plan"})


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


def test_planner_output_rejects_null_collection_fields() -> None:
    with pytest.raises(ValidationError):
        PlannerGraphOutput.model_validate({
            "action": "apply_graph",
            "tasks": None,
            "remove_task_ids": None,
        })


def test_planner_output_rejects_runtime_needs() -> None:
    with pytest.raises(ValidationError, match="needs"):
        PlannerGraphOutput.model_validate({
            "action": "apply_graph",
            "tasks": [{
                "task_id": "reader",
                "executor": "viewer",
                "intent": "Read source",
                "instructions": "Read the source",
                "needs": [{"key": "source", "description": "Source text"}],
            }],
        })


def test_planner_schema_hides_runtime_needs_but_runtime_patch_keeps_contract() -> None:
    schema = PlannerGraphOutput.model_json_schema()
    planner_task_schema = schema["$defs"]["PlannerPlannedTask"]
    assert "needs" not in planner_task_schema["properties"]

    patch = PlannerGraphOutput.model_validate({
        "action": "apply_graph",
        "tasks": [{
            "task_id": "reader",
            "executor": "viewer",
            "intent": "Read source",
            "instructions": "Read the source",
        }],
    }).to_plan_patch(plan={"revision": 0, "tasks": {}})

    assert patch.tasks[0].needs == []


def test_planner_output_rejects_removed_completion_action() -> None:
    with pytest.raises(ValidationError):
        PlannerGraphOutput.model_validate({"action": "complete"})


def test_graph_task_can_request_replan_after_success() -> None:
    task = PlannedTask.model_validate({
        "task_id": "reader",
        "executor": "context_reader",
        "intent": "Read the document",
        "instructions": "Return bounded findings",
        "on_success": "replan",
    })

    assert task.on_success.value == "replan"


def test_planner_checkpoint_is_a_control_node_without_an_executor() -> None:
    task = PlannedTask.model_validate({
        "task_id": "after_discovery",
        "kind": "planner",
        "intent": "Assess findings",
        "instructions": "Determine the next graph segment",
        "depends_on": ["discover"],
    })

    assert task.kind is PlanNodeKind.PLANNER
    assert task.executor is None


def test_planner_checkpoint_rejects_agent_fields() -> None:
    with pytest.raises(ValidationError, match="cannot declare executor"):
        PlannedTask.model_validate({
            "task_id": "after_discovery",
            "kind": "planner",
            "executor": "planner",
            "intent": "Assess findings",
            "instructions": "Determine the next graph segment",
        })


def test_synthesis_checkpoint_is_executorless_and_has_no_dependencies() -> None:
    task = PlannedTask.model_validate({
        "task_id": "synthesize",
        "kind": "synthesis",
        "intent": "Answer the actual user question",
        "instructions": "State the conclusion and relevant caveats.",
    })

    assert task.kind is PlanNodeKind.SYNTHESIS
    assert task.executor is None

    with pytest.raises(ValidationError, match="cannot declare dependencies"):
        PlannedTask.model_validate({
            "task_id": "synthesize",
            "kind": "synthesis",
            "intent": "Answer",
            "instructions": "Answer",
            "depends_on": ["inspect"],
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
        "available_artifacts": [],
        "needs": [],
        "last_failure": None,
        "user_response": "blue",
        "available_agents": [],
        "memory_context": [{"scope": "user", "subject": "role", "value": "engineer"}],
    })())

    assert payload["mode"] == "replan"
    assert payload["replan_reason"] == "technical_failure"
    assert payload["user_response"] == "blue"
    assert payload["memory_context"] == [{"scope": "user", "subject": "role", "value": "engineer"}]
    assert payload["plan"] == {
        "has_existing_graph": True,
        "status": "active",
        "tasks": {"inspect": {"task_id": "inspect", "status": "completed"}},
    }
    assert payload["completed_outputs"] == {}
    assert payload["terminal_synthesis"]["kind"] == "synthesis"


def test_planner_input_keeps_full_graph_and_checkpoint_metadata() -> None:
    payload = PlannerInputBuilder().build_graph_request(type("Request", (), {
        "goal": "Assess tickets",
        "trigger": "planner_checkpoint",
        "plan": {
            "revision": 2,
            "status": "active",
            "tasks": {
                "discover": {
                    "task_id": "discover",
                    "status": "completed",
                    "result": {"outputs": {"tickets": [{"key": "OPS-1"}]}},
                },
            },
        },
        "completed_outputs": {"discover": {"tickets": [{"key": "OPS-1"}]}},
        "available_artifacts": [],
        "needs": [],
        "last_failure": None,
        "user_response": None,
        "available_agents": [],
        "memory_context": [],
        "checkpoint": {
            "task_id": "after_discovery",
            "intent": "Assess tickets",
            "instructions": "Determine next steps",
            "depends_on": ["discover"],
        },
    })())

    assert payload["plan"]["tasks"]["discover"]["result"]["outputs"]["tickets"] == [{"key": "OPS-1"}]
    assert payload["checkpoint"]["task_id"] == "after_discovery"
