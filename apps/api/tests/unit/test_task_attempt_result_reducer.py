import pytest

from app.runtime.orchestrator_contracts import TaskCompletionDeclaration, TaskRequest
from app.runtime.task_result_reducer import TaskAttemptResultReducer


def reduce(payload, *, verified=None, **request):
    return TaskAttemptResultReducer().reduce(
        request=TaskRequest(task_id="task", executor="agent", intent="read", instructions="read", **request),
        declaration=TaskCompletionDeclaration.model_validate(payload), verified=verified or {},
    )


@pytest.mark.parametrize("value", [None, "", "   ", 0, False, [], {}, {"name": None, "enabled": False}])
def test_actual_values_are_preserved_even_when_advisory_schema_disagrees(value):
    result = reduce({"completion": "fulfilled", "structured_response": {"value": value}},
                    expected_outputs=[{"key": "value", "description": "Value", "schema": {"type": "string", "minLength": 1}}])
    assert result.outcome.value == "completed"
    assert result.outputs == {"value": value}
    assert result.structured_response == {"value": value}


@pytest.mark.parametrize("verified", [{}, {"receipts": [{"inline_complete": False, "source_complete": False}]},
                                      {"receipts": [{"call_id": "sql", "analysis": {"query_complete": False}}]}])
def test_coverage_and_retrieval_do_not_override_agent_completion(verified):
    result = reduce({"completion": "fulfilled", "answer": "First page only", "structured_response": [1]},
                    verified=verified, freshness_policy="require_retrieval",
                    expected_outputs=[{"key": "rows", "description": "Rows", "require_complete_source": True}])
    assert result.outcome.value == "completed"
    assert result.answer == "First page only"
    assert result.verified == verified


@pytest.mark.parametrize("status,outcome", [("fulfilled", "completed"), ("needs", "needs_dependency"), ("unfulfillable", "unfulfillable")])
def test_agent_completion_is_preserved_with_malformed_advisory_schema(status, outcome):
    payload = {"completion": status, "structured_response": {"found": 1}}
    if status == "needs":
        payload["needs"] = [{"ref": "target", "key": "target", "description": "Select target"}]
    result = reduce(payload, response_spec={"mode": "structured", "schema": {"type": "unknown"}})
    assert result.outcome.value == outcome
    assert result.diagnostics[0]["code"] == "advisory_schema_invalid"


def test_runtime_sources_and_unrequested_files_are_preserved():
    verified = {"sources": [{"url": "https://example.test/device"}], "artifacts": [{"artifact_id": "f"}]}
    result = reduce({"completion": "unfulfillable", "answer": "File created; metadata update failed"}, verified=verified)
    assert result.attachments == verified["artifacts"]
    assert result.sources == verified["sources"]
    assert result.outcome.value == "unfulfillable"


def test_deleted_file_does_not_fulfil_required_attachment():
    result = reduce({"completion": "fulfilled"}, response_spec={"mode": "artifact"},
                    verified={"artifacts": [{"artifact_id": "f", "deleted": True}]})
    assert result.attachments == []
    assert result.reason_code == "required_artifact_missing"


def test_missing_file_does_not_erase_needs_or_partial_result():
    result = reduce({"completion": "needs", "answer": "Need target", "structured_response": {"found": 1},
                     "needs": [{"ref": "target", "key": "target", "description": "Target"}]},
                    response_spec={"mode": "artifact"})
    assert result.outcome.value == "needs_dependency"
    assert result.needs[0].ref == "target"
    assert result.structured_response == {"found": 1}
