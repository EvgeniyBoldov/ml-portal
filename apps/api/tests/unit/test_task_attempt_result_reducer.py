import pytest

from app.runtime.orchestrator_contracts import (
    DiscoveredNeed,
    TaskCompletionDeclaration, TaskOutputFulfillment, TaskOutputSpec,
    TaskOutcome, TaskRequest,
)
from app.runtime.task_result_reducer import TaskAttemptResultReducer


def _request(**overrides):
    return TaskRequest(task_id="task", executor="agent", intent="answer", instructions="answer", **overrides)


def _declaration(**overrides):
    return TaskCompletionDeclaration(completion="fulfilled", report="Found the answer", **overrides)


def _reduce(request, declaration, verified=None):
    return TaskAttemptResultReducer().reduce(request=request, declaration=declaration, verified=verified or {})


def test_direct_output_fulfils_without_tool_receipt() -> None:
    result = _reduce(_request(expected_outputs=[TaskOutputSpec(key="answer", description="Answer")]), _declaration(outputs={"answer": {"kind": "value", "value": "known fact"}}))
    assert result.outcome is TaskOutcome.COMPLETED
    assert result.outputs["answer"] == "known fact"


def test_schema_validates_direct_output_value() -> None:
    result = _reduce(_request(expected_outputs=[TaskOutputSpec(key="tasks", description="Tasks", json_schema={"type": "array"})]), _declaration(outputs={"tasks": {"kind": "value", "value": [{"key": "NIMS-3334"}]}}))
    assert result.outcome is TaskOutcome.COMPLETED


def test_schema_rejects_wrong_direct_output_value() -> None:
    result = _reduce(_request(expected_outputs=[TaskOutputSpec(key="tasks", description="Tasks", json_schema={"type": "array"})]), _declaration(outputs={"tasks": {"kind": "value", "value": {"items": []}}}))
    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "output_contract_invalid"


def test_freshness_is_verified_by_runtime() -> None:
    result = _reduce(_request(freshness_policy="require_retrieval"), _declaration())
    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "fresh_retrieval_missing"


def test_named_jira_issue_requires_jira_get_issue_receipt() -> None:
    request = _request(
        inputs={"jira_task_id": "NIMS-3451"},
        freshness_policy="require_retrieval",
        expected_outputs=[TaskOutputSpec(key="task", description="Task")],
    )
    declaration = _declaration(outputs={"task": {"kind": "value", "value": "invented"}})
    result = _reduce(
        request,
        declaration,
        {"fresh_retrieval": True, "receipts": [{"canonical_operation": "jira_search_issues"}]},
    )
    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "required_retrieval_operation_missing"

    result = _reduce(
        request,
        declaration,
        {"fresh_retrieval": True, "receipts": [{"canonical_operation": "jira_get_issue"}]},
    )
    assert result.outcome is TaskOutcome.COMPLETED


def test_explicit_required_operations_override_identifier_heuristics() -> None:
    request = _request(
        inputs={"required_retrieval_operations": ["jira_get_issue"]},
        freshness_policy="require_retrieval",
    )
    result = _reduce(
        request,
        _declaration(),
        {"fresh_retrieval": True, "receipts": [{"canonical_operation": "jira_search_issues"}]},
    )
    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "required_retrieval_operation_missing"


def test_jira_key_requires_authoritative_issue_receipt() -> None:
    request = _request(inputs={"jira_key": "NIMS-3451"}, freshness_policy="require_retrieval")
    result = _reduce(
        request,
        _declaration(),
        {"fresh_retrieval": True, "receipts": [{"canonical_operation": "jira_search_issues"}]},
    )
    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "required_retrieval_operation_missing"


def test_needs_is_not_a_successful_task() -> None:
    declaration = TaskCompletionDeclaration(completion="needs", report="Need target", needs=[DiscoveredNeed(ref="target", key="target", description="Target")])
    assert _reduce(_request(), declaration).outcome is TaskOutcome.NEEDS_DEPENDENCY


def test_receipt_must_be_selected_and_verified() -> None:
    request = _request(expected_outputs=[TaskOutputSpec(key="policy", description="Policy", fulfillment=TaskOutputFulfillment.VERIFIED_RECEIPT, receipt_operations=["collection.document.search"])])
    declaration = _declaration(outputs={"policy": {"kind": "evidence", "refs": ["result_1"]}})
    verified = {"receipts": [{"result_ref": "result_1", "canonical_operation": "collection.document.search"}]}
    assert _reduce(request, declaration, verified).outcome is TaskOutcome.COMPLETED


def test_receipt_can_use_the_evidence_call_id_seen_by_the_agent() -> None:
    request = _request(expected_outputs=[TaskOutputSpec(key="policy", description="Policy", fulfillment=TaskOutputFulfillment.VERIFIED_RECEIPT, receipt_operations=["collection.document.search"])])
    declaration = _declaration(outputs={"policy": {"kind": "evidence", "refs": ["call-1"]}})
    verified = {"receipts": [{"result_ref": "result_1", "call_id": "call-1", "canonical_operation": "collection.document.search"}]}
    result = _reduce(request, declaration, verified)
    assert result.outcome is TaskOutcome.COMPLETED
    assert result.evidence_selections[0].result_ref == "result_1"


def test_artifact_must_be_selected_from_runtime_ledger() -> None:
    request = _request(expected_outputs=[TaskOutputSpec(key="report", description="Report", fulfillment=TaskOutputFulfillment.ARTIFACT)])
    declaration = _declaration(outputs={"report": {"kind": "artifact", "refs": ["artifact-1"]}})
    assert _reduce(request, declaration, {"artifacts": [{"artifact_ref": "artifact-1", "artifact_id": "artifact-1"}]}).outcome is TaskOutcome.COMPLETED


def test_unknown_artifact_selection_fails_task() -> None:
    request = _request(expected_outputs=[TaskOutputSpec(key="report", description="Report", fulfillment=TaskOutputFulfillment.ARTIFACT)])
    declaration = _declaration(outputs={"report": {"kind": "artifact", "refs": ["invented"]}})
    result = _reduce(request, declaration)
    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "output_contract_invalid"


def test_nullable_value_is_not_treated_as_a_missing_output() -> None:
    request = _request(expected_outputs=[TaskOutputSpec(key="description", description="Description", schema={"type": ["string", "null"]})])
    result = _reduce(request, _declaration(outputs={"description": {"kind": "value", "value": None}}))
    assert result.outcome is TaskOutcome.COMPLETED
    assert "description" in result.outputs and result.outputs["description"] is None


@pytest.mark.parametrize(("schema", "expected"), [
    ({"type": "string"}, ""),
    ({"type": "array"}, []),
    ({"type": "object"}, {}),
])
def test_null_is_normalized_to_the_empty_value_allowed_by_contract(schema, expected) -> None:
    request = _request(expected_outputs=[TaskOutputSpec(key="value", description="Value", schema=schema)])
    result = _reduce(request, _declaration(outputs={"value": {"kind": "value", "value": None}}))

    assert result.outcome is TaskOutcome.COMPLETED
    assert result.outputs["value"] == expected
    assert result.output_states["value"]["normalized_from"] == "null"


def test_null_is_not_coerced_when_empty_string_breaks_contract_constraints() -> None:
    request = _request(expected_outputs=[TaskOutputSpec(
        key="value", description="Value", schema={"type": "string", "minLength": 1},
    )])
    result = _reduce(request, _declaration(outputs={"value": {"kind": "value", "value": None}}))

    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "output_contract_invalid"
