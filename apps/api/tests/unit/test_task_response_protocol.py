import pytest

from app.runtime.orchestrator_contracts import TaskCompletionDeclaration, TaskOutputSpec, TaskRequest
from app.runtime.task_result_reducer import TaskAttemptResultReducer


def reduce(payload, *, outputs=None, verified=None):
    return TaskAttemptResultReducer().reduce(
        request=TaskRequest(task_id="t", executor="agent", intent="read", instructions="read",
                            expected_outputs=outputs or []),
        declaration=TaskCompletionDeclaration.model_validate(payload), verified=verified or {},
    )


def test_schema_deviation_preserves_data_and_agent_completion():
    result = reduce({"completion": "fulfilled", "answer": "IP absent",
                     "structured_response": {"devices": [{"name": "a", "primary_ip": None}]}},
                    outputs=[TaskOutputSpec(key="devices", description="Devices", schema={"type": "string"})])
    assert result.outcome.value == "completed"
    assert result.structured_response["devices"][0]["primary_ip"] is None
    assert result.answer == "IP absent"
    assert result.diagnostics


def test_needs_survives_partial_data_schema_deviation():
    result = reduce({"completion": "needs", "structured_response": {"found": 1},
                     "needs": [{"ref": "n", "key": "target", "description": "Choose target"}]},
                    outputs=[TaskOutputSpec(key="found", description="Found", schema={"type": "array"})])
    assert result.outcome.value == "needs_dependency"
    assert result.needs[0].ref == "n"


def test_runtime_artifact_needs_no_model_selection():
    spec = TaskOutputSpec(key="file", description="File", fulfillment="artifact")
    result = reduce({"completion": "fulfilled"}, outputs=[spec],
                    verified={"artifacts": [{"artifact_id": "f", "artifact_ref": "f"}]})
    assert result.outcome.value == "completed"
    assert result.attachments[0]["artifact_id"] == "f"
    missing = reduce({"completion": "fulfilled", "answer": "File creation failed"}, outputs=[spec])
    assert missing.reason_code == "required_artifact_missing"
    assert missing.answer == "File creation failed"


def test_arbitrary_result_and_empty_search_are_accepted():
    assert reduce({"completion": "fulfilled", "structured_response": []}).outcome.value == "completed"
    assert reduce({"completion": "fulfilled", "structured_response": {"unexpected": 1}}).outcome.value == "completed"


def test_legacy_result_is_adapted_without_normalizing_values():
    result = reduce({"completion": "fulfilled", "report": "Found",
                     "outputs": {"devices": {"kind": "value", "value": [None]}}})
    assert result.answer == "Found"
    assert result.structured_response == {"devices": [None]}


def finish(store, plan_id, task_id, payload):
    from app.runtime.orchestrator_contracts import TaskExecutionReceipt
    store.claim_task(plan_id, task_id)
    request = TaskRequest.model_validate(store.task_request(plan_id, task_id))
    declaration = TaskCompletionDeclaration.model_validate(payload)
    result = TaskAttemptResultReducer().reduce(request=request, declaration=declaration, verified={})
    store.finish_attempt(plan_id, task_id, execution=TaskExecutionReceipt(declaration=declaration), result=result)


def handoff_plan(selector):
    from app.runtime.orchestrator_contracts import IterationProposal, SchedulerActionKind
    from app.runtime.plan_store import InMemoryPlanStore
    store = InMemoryPlanStore()
    plan = store.create(goal="g", root_run_id="r", tenant_id="t")
    store.apply_iteration(plan["id"], IterationProposal.model_validate({"terminal": "planner", "tasks": [
        {"task_id": "source", "executor": "agent", "intent": "get", "instructions": "get",
         "response_spec": {"mode": "structured", "schema": {"type": "string"}}},
        {"task_id": "old", "executor": "agent", "intent": "use", "instructions": "use"},
    ]}))
    finish(store, plan["id"], "source", {"completion": "fulfilled", "structured_response": {"rows": [None]}})
    finish(store, plan["id"], "old", {"completion": "needs", "answer": "Need rows",
                                     "needs": [{"ref": "n", "key": "rows", "description": "Rows", "schema": {"type": "integer"}}]})
    store.claim_checkpoint(plan["id"], SchedulerActionKind.INVOKE_PLANNER)
    proposal = IterationProposal.model_validate({"terminal": "planner", "tasks": [
        {"task_id": "consumer", "executor": "agent", "intent": "use", "instructions": "use"}],
        "bindings": [{"need_task_id": "old", "need_ref": "n", "producer_task_id": "source", "output_key": selector,
                      "consumer_task_id": "consumer", "consumer_input_key": "rows"}],
        "resolutions": [{"task_id": "old", "action": "continue_with_tasks", "replacement_task_ids": ["consumer"], "reason": "Use actual rows"}]})
    from app.runtime.orchestrator import GraphOrchestrator
    GraphOrchestrator._compile(proposal, [{"slug": "agent"}], {"tasks": list(plan["tasks"].values()), "needs": plan["needs"]})
    store.apply_iteration(plan["id"], proposal)
    return store, plan


def test_prior_completed_result_handoff_preserves_schema_deviation_and_null():
    store, plan = handoff_plan("/structured_response/rows")
    assert store.next_decision(plan["id"]).task_id == "consumer"
    store.claim_task(plan["id"], "consumer")
    request = store.task_request(plan["id"], "consumer")
    assert request["inputs"]["rows"] == [None]
    assert request["dependency_outputs"] == {}
    assert plan["tasks"]["source"]["result"]["diagnostics"]


def test_missing_binding_path_replans_only_consumer():
    store, plan = handoff_plan("/structured_response/missing")
    assert store.next_decision(plan["id"]).kind.value == "invoke_planner"
    assert plan["tasks"]["source"]["status"] == "completed"
    assert plan["tasks"]["consumer"]["status"] == "blocked"
    assert plan["tasks"]["consumer"]["result"]["reason_code"] == "binding_result_missing"
    assert plan["tasks"]["consumer"]["attempts"] == 0


def test_registered_contract_is_advisory_and_remains_typed_for_persistence():
    from app.runtime.orchestrator import GraphOrchestrator
    from app.runtime.orchestrator_contracts import IterationProposal
    proposal = IterationProposal.model_validate({"terminal": "planner", "tasks": [{
        "task_id": "a", "executor": "agent", "intent": "use", "instructions": "use", "inputs": {"id": None},
        "contract": {"mode": "registered", "contract_id": "read"}}]})
    compiled = GraphOrchestrator._compile(proposal, [{"slug": "agent", "task_contracts": [{
        "contract_id": "read", "version": 1, "description": "Read",
        "input_schema": {"type": "object", "required": ["id"], "properties": {"id": {"type": "integer"}}},
        "response_spec": {"mode": "structured", "schema": {"type": "unknown"}}}]}], {"tasks": [], "needs": []})
    assert compiled.tasks[0].inputs == {"id": None}
    assert compiled.tasks[0].contract.model_dump()["contract_id"] == "read"
    assert compiled.tasks[0].response_spec.json_schema == {"type": "unknown"}


@pytest.mark.asyncio
async def test_large_task_context_is_saved_without_cutting_json(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.runtime import agent_executor as module
    from app.runtime.agent_executor import AgentExecutor
    save = AsyncMock(return_value={"result_id": "stored", "sql_ref": "result_stored"})
    monkeypatch.setattr(module, "ToolResultStore", lambda: SimpleNamespace(save=save))
    task = TaskRequest(task_id="a", executor="agent", intent="use", instructions="use", inputs={"rows": ["x" * 10000]})
    ctx = SimpleNamespace(extra={"runtime_root_run_id": "root"}, tenant_id="t", user_id="u")
    bounded = await AgentExecutor._prepare_task_context(task, ctx, "execution")
    assert save.await_args.kwargs["payload"] == task.inputs
    assert bounded.inputs["saved_context"]["sql_ref"] == "result_stored"
    assert task.inputs == {"rows": ["x" * 10000]}
    assert "result_stored" in AgentExecutor._build_sub_messages([], bounded, "g")[-1]["content"]
