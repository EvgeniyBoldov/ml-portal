from __future__ import annotations

from app.runtime.agent_executor import AgentExecutor
import pytest

from app.runtime.orchestrator import GraphOrchestrator, OrchestratorEvent
from app.runtime.entity_ids import runtime_attempt_id, runtime_task_id
from app.runtime.orchestrator_contracts import (
    AgentExecutionResult, IterationProposal, NeedBinding, PlannedTask,
    TaskRequest, TaskResolution, TerminalKind,
)
from app.runtime.plan_store import InMemoryPlanStore, PlanValidationError
from app.runtime.synthesis_context import SynthesisContextBuilder
from app.runtime.task_result_reducer import TaskAttemptResultReducer


def _task(*, expected_outputs: list[dict] | None = None) -> TaskRequest:
    return TaskRequest(
        task_id="task",
        executor="research",
        intent="inspect",
        instructions="Inspect the supplied project.",
        inputs={"project_key": "project-1", "filters": {"active": True}},
        expected_outputs=expected_outputs or [],
    )


def test_agent_receives_task_inputs_and_complete_output_contract() -> None:
    request = _task(expected_outputs=[{
        "key": "result", "description": "Structured finding", "required": True,
        "schema": {"type": "object", "required": ["name"], "properties": {"name": {"type": "string"}}},
    }])

    message = AgentExecutor._build_sub_messages([], request, "goal")[-1]["content"]

    assert '"project_key": "project-1"' in message
    assert "Structured finding" in message
    assert '"required": ["name"]' in message
    assert "Never emit null" in message


def test_partial_artifact_is_runtime_verified_before_synthesis() -> None:
    request = _task(expected_outputs=[{
        "key": "file", "description": "Generated file", "fulfillment": "artifact",
    }])
    execution = AgentExecutionResult(
        completion="unfulfillable",
        description="partial result",
        outputs={"file": {"artifacts": [{"artifact_id": "agent-claimed"}]}},
        limitation={"code": "incomplete", "message": "The operation did not finish."},
    )

    result = TaskAttemptResultReducer().reduce(request=request, execution=execution)

    assert result.outputs == {}


def test_latest_resolution_controls_synthesis_and_report_unresolved_is_visible() -> None:
    plan = {
        "goal": "goal",
        "iterations": [{"id": "iteration", "sequence": 1, "terminal": "synthesis", "synthesis_brief": {"purpose": "answer"}}],
        "tasks": {"task": {
            "iteration_id": "iteration", "status": "unfulfillable",
            "result": {"description": "partial", "outputs": {"answer": {"text": "old"}},
                       "limitation": {"code": "incomplete", "message": "Still incomplete"}},
        }},
        "resolutions": [
            {"task_id": "task", "action": "accept_partial", "output_keys": ["answer"], "reason": "old"},
            {"task_id": "task", "action": "report_unresolved", "output_keys": [], "reason": "current"},
        ],
    }

    context = SynthesisContextBuilder().build(plan=plan, iteration_id="iteration")

    assert context["completed_task_reports"] == []
    assert context["limitations"] == [{"task_id": "task", "status": "unfulfillable", "reason_code": "incomplete", "message": "Still incomplete"}]
    assert context["resolution_decisions"] == [{"task_id": "task", "action": "report_unresolved", "output_keys": [], "reason": "current"}]


def test_output_schema_uses_full_json_schema_validation() -> None:
    assert not TaskAttemptResultReducer._matches_schema(
        {"count": -1},
        {"type": "object", "properties": {"count": {"type": "integer", "minimum": 0}}},
    )


def test_reducer_drops_undeclared_outputs_and_validates_text_as_bound_value() -> None:
    request = _task(expected_outputs=[{
        "key": "name", "description": "Name", "schema": {"type": "string"},
    }])
    execution = AgentExecutionResult(
        completion="fulfilled",
        description="done",
        outputs={"name": {"text": "Alice"}, "internal": {"text": "must not escape"}},
    )

    result = TaskAttemptResultReducer().reduce(request=request, execution=execution)

    assert result.outcome.value == "completed"
    assert set(result.outputs) == {"name"}


def test_verified_receipt_must_match_the_declared_operation() -> None:
    request = _task(expected_outputs=[{
        "key": "write", "description": "Write receipt",
        "fulfillment": "verified_receipt", "receipt_operations": ["file.generate"],
    }])
    execution = AgentExecutionResult(
        completion="fulfilled", description="done", outputs={"write": {"text": "done"}},
        verified={"receipts": [{"operation": "file.read"}]},
    )

    rejected = TaskAttemptResultReducer().reduce(request=request, execution=execution)
    accepted = TaskAttemptResultReducer().reduce(
        request=request,
        execution=execution.model_copy(update={
            "verified": {"receipts": [{"canonical_operation": "file.generate"}]},
        }),
    )

    assert rejected.outcome.value == "unfulfillable"
    assert accepted.outcome.value == "completed"


def test_binding_injects_the_schema_validated_value_not_its_storage_wrapper() -> None:
    store = InMemoryPlanStore()
    plan = store.create(goal="g", root_run_id="run", tenant_id="tenant")
    plan["tasks"] = {
        "producer": {"result": {"outputs": {"value": {"description": None, "text": None, "data": {"id": 7}, "artifacts": []}}}},
        "consumer": {
            "task_id": "consumer", "executor": "research", "intent": "use", "instructions": "use",
            "inputs": {}, "depends_on": ["producer"], "expected_outputs": [], "freshness_policy": "allow_memory",
        },
    }
    plan["bindings"] = [{
        "producer_task_id": "producer", "output_key": "value",
        "consumer_task_id": "consumer", "consumer_input_key": "resolved",
    }]

    assert store.task_request(plan["id"], "consumer")["inputs"]["resolved"] == {"id": 7}


def test_artifact_outputs_have_one_runtime_owned_owner() -> None:
    with pytest.raises(ValueError, match="at most one artifact output"):
        IterationProposal.model_validate({
            "terminal": "planner",
            "tasks": [{
                "task_id": "write", "executor": "writer", "intent": "write", "instructions": "write",
                "expected_outputs": [
                    {"key": "first", "description": "first", "fulfillment": "artifact"},
                    {"key": "second", "description": "second", "fulfillment": "artifact"},
                ],
            }],
        })


def test_binding_schema_must_match_the_discovered_need() -> None:
    proposal = IterationProposal(
        terminal=TerminalKind.PLANNER,
        tasks=[
            PlannedTask(task_id="producer", executor="research", intent="get", instructions="get", expected_outputs=[{"key": "value", "description": "value", "schema": {"type": "string"}}]),
            PlannedTask(task_id="consumer", executor="research", intent="use", instructions="use", depends_on=["producer"]),
        ],
        bindings=[NeedBinding(need_task_id="old", need_ref="missing", producer_task_id="producer", output_key="value", consumer_task_id="consumer", consumer_input_key="value")],
        resolutions=[TaskResolution(task_id="old", action="continue_with_tasks", replacement_task_ids=["consumer"], reason="supply missing input")],
    )
    ledger = {"tasks": [{"task_id": "old", "status": "needs_dependency", "result": {"outputs": {}}}], "resolutions": [], "needs": [{"task_id": "old", "ref": "missing", "schema": {"type": "integer"}}]}

    with pytest.raises(PlanValidationError, match="schema"):
        GraphOrchestrator._compile(proposal, [{"slug": "research"}], ledger)


def test_completed_task_resolution_is_ignored_when_planner_moves_to_synthesis() -> None:
    proposal = IterationProposal(
        terminal=TerminalKind.SYNTHESIS,
        synthesis_brief={
            "user_question": "goal",
            "planned_work": "inspect",
            "purpose": "answer",
            "answer_requirements": "summary",
        },
        resolutions=[TaskResolution(
            task_id="task",
            action="accept_partial",
            output_keys=["answer"],
            reason="already completed",
        )],
    )
    ledger = {
        "tasks": [{
            "task_id": "task",
            "status": "completed",
            "result": {"outputs": {"answer": {"text": "done"}}},
        }],
        "resolutions": [],
        "needs": [],
    }

    compiled = GraphOrchestrator._compile(proposal, [], ledger)

    assert compiled.resolutions == []


def test_attempt_failure_event_has_exact_attempt_identifier() -> None:
    event = OrchestratorEvent(type="task_attempt_failed", plan_id="plan", task_id="task", attempt=2, error={"code": "timeout"}).to_runtime_event()

    task_entity_id = runtime_task_id("plan", "task")
    assert event.data["entity_id"] == runtime_attempt_id(task_entity_id, 2)
    assert event.data["parent_entity_id"] == task_entity_id
    assert event.data["task_id"] == "task"


def test_applied_iteration_event_is_owned_by_the_persisted_iteration() -> None:
    event = OrchestratorEvent(
        type="iteration_created", plan_id="plan", iteration_id="iteration",
        trigger="initial", terminal="planner", proposal={"terminal": "planner", "tasks": []},
    ).to_runtime_event()

    assert event.data["parent_entity_type"] == "planner_iteration"
    assert event.data["parent_entity_id"] == "iteration"
    assert event.data["iteration_id"] == "iteration"
