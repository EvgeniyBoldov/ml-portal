import json

import pytest
from jsonschema import Draft202012Validator

from app.runtime.agent_executor import AgentExecutor
from app.runtime.orchestrator_contracts import (
    TaskRequest, parse_task_completion_declaration, task_completion_json_schema,
)


def request():
    return TaskRequest(task_id="task", executor="agent", intent="answer", instructions="Answer",
                       expected_outputs=[{"key": "answer", "description": "Answer", "schema": {"type": ["string", "null"]}}])


@pytest.mark.parametrize("absent", [None, "", "   "])
def test_envelope_absence_normalizes_to_schema_valid_defaults(absent):
    declaration = parse_task_completion_declaration(json.dumps({
        "completion": "fulfilled", "report": "done", "outputs": {"answer": {"kind": "value", "value": None}},
        "needs": absent, "coverage": absent, "limitation": absent,
    }))
    assert declaration.needs == declaration.coverage == []
    assert declaration.limitation is None
    Draft202012Validator(task_completion_json_schema(request())).validate(declaration.model_dump(mode="json", by_alias=True))
    assert AgentExecutor._terminal_validation_errors(json.dumps(declaration.model_dump(mode="json", by_alias=True)), task=request(), verified={}) == []


def test_minimal_needs_declaration_round_trips_through_provider_schema():
    declaration = parse_task_completion_declaration(json.dumps({
        "completion": "needs", "report": "Target needed", "needs": [{
            "ref": "target", "key": "target", "description": "Target", "context": None, "schema": "",
        }],
    }))
    Draft202012Validator(task_completion_json_schema(request())).validate(declaration.model_dump(mode="json", by_alias=True))


@pytest.mark.parametrize("completion", ["fulfilled", "needs", "unfulfillable"])
def test_completion_rules_match_provider_schema(completion):
    payload = {"completion": completion, "report": "done", "outputs": {"answer": {"kind": "value", "value": None}}, "needs": []}
    if completion == "needs":
        payload["needs"] = [{"ref": "target", "key": "target", "description": "Target"}]
    if completion == "unfulfillable":
        payload["limitation"] = {"code": "blocked", "message": "Target unavailable", "action": ""}
    declaration = parse_task_completion_declaration(json.dumps(payload))
    Draft202012Validator(task_completion_json_schema(request())).validate(declaration.model_dump(mode="json", by_alias=True))


@pytest.mark.parametrize("payload", [
    {"completion": "fulfilled", "report": "   "},
    {"completion": "fulfilled", "report": "done", "unknown": None},
    {"completion": "unfulfillable", "report": "blocked", "limitation": ""},
    {"completion": "needs", "report": "needs", "needs": None},
    {"completion": "fulfilled", "report": "done", "outputs": {"answer": {"kind": "value"}}},
])
def test_absence_does_not_hide_required_fields_or_unknown_fields(payload):
    with pytest.raises(ValueError):
        parse_task_completion_declaration(json.dumps(payload))


def test_task_validation_feedback_identifies_missing_required_output():
    errors = AgentExecutor._terminal_validation_errors('{"completion":"fulfilled","report":"done"}', task=request(), verified={})
    assert errors == ["required_output_missing: The task result did not fulfill required outputs: answer"]


def test_duplicate_output_keys_are_rejected_before_execution():
    task = request().model_dump(mode="json", by_alias=True)
    task["expected_outputs"].append(task["expected_outputs"][0])
    with pytest.raises(ValueError, match="unique keys"):
        TaskRequest.model_validate(task)


def test_validation_feedback_can_be_repaired_using_existing_sql_receipt():
    task = TaskRequest(task_id="counts", executor="agent", intent="answer", instructions="Answer",
                       expected_outputs=[{"key": "counts", "description": "Counts", "schema": {"type": "array"}}])
    payload = {"completion": "fulfilled", "report": "done", "outputs": {"counts": {"kind": "value", "value": [{"type": "a", "count": 1}]}},
               "coverage": [{"output_key": "counts", "result_id": "query-result", "query_call_ids": ["invented"]}], "limitation": None}
    verified = {"receipts": [{"result_id": "source", "inline_complete": False},
                             {"result_id": "query-result", "call_id": "observed-query", "inline_complete": True, "analysis": {
                                 "mode": "sql", "result_id": "query-result", "query_result_stored": True,
                                 "query_complete": True, "source_result_ids": ["source"], "source_complete": True,
                             }}]}
    assert AgentExecutor._terminal_validation_errors(json.dumps(payload), task=task, verified=verified) == ["outputs.counts: stored_result_array_coverage_unverified"]
    payload["coverage"][0]["query_call_ids"] = ["observed-query"]
    assert AgentExecutor._terminal_validation_errors(json.dumps(payload), task=task, verified=verified) == []


@pytest.mark.parametrize("refs", [["", "  "], [None], None, ""])
def test_blank_refs_do_not_create_evidence(refs):
    with pytest.raises(ValueError):
        parse_task_completion_declaration(json.dumps({
            "completion": "fulfilled", "report": "done", "outputs": {"answer": {"kind": "evidence", "refs": refs}},
        }))


def test_task_rejection_event_exposes_validation_reason_without_output_data():
    from app.runtime.orchestrator import OrchestratorEvent
    event = OrchestratorEvent(type="task_unfulfillable", plan_id="plan", task_id="task", outcome="unfulfillable",
                              reason_code="output_contract_invalid", output_states={"answer": {"status": "invalid", "reason": "value_schema_invalid"}}).to_runtime_event()
    assert event.data["reason_code"] == "output_contract_invalid"
    assert event.data["output_states"]["answer"]["reason"] == "value_schema_invalid"
