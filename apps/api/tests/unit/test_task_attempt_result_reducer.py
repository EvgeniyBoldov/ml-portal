import pytest

from app.runtime.orchestrator_contracts import (
    DiscoveredNeed, OutputCoverageClaim,
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


def test_sql_result_receipt_covers_an_array_output() -> None:
    result_id = "sql-result-id"
    call_id = "sql-call-id"
    request = _request(expected_outputs=[TaskOutputSpec(key="rows", description="Rows", json_schema={"type": "array"}, require_complete_source=True)])
    declaration = _declaration(
        outputs={"rows": {"kind": "value", "value": [{"key": "OPS-1"}]}},
        coverage=[OutputCoverageClaim(output_key="rows", result_id=result_id, query_call_ids=[call_id])],
    )
    verified = {"receipts": [{
        "result_id": result_id, "call_id": call_id,
        "inline_complete": False, "success": True,
        "analysis": {
            "mode": "sql", "result_id": result_id, "row_count": 1,
            "source_result_ids": ["source-1"], "query_result_stored": True,
            "source_complete": True,
        },
    }]}
    assert _reduce(request, declaration, verified).outcome is TaskOutcome.COMPLETED


def test_sql_result_receipt_does_not_claim_complete_from_incomplete_source() -> None:
    result_id = "sql-result-id"
    call_id = "sql-call-id"
    request = _request(expected_outputs=[TaskOutputSpec(key="rows", description="Rows", json_schema={"type": "array"}, require_complete_source=True)])
    declaration = _declaration(
        outputs={"rows": {"kind": "value", "value": [{"key": "OPS-1"}]}},
        coverage=[OutputCoverageClaim(output_key="rows", result_id=result_id, query_call_ids=[call_id])],
    )
    verified = {"receipts": [{
        "result_id": result_id, "call_id": call_id,
        "inline_complete": False, "success": True,
        "analysis": {"mode": "sql", "result_id": result_id, "row_count": 1,
                     "query_result_stored": True, "source_complete": False},
    }]}
    result = _reduce(request, declaration, verified)
    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.output_states["rows"]["reason"] == "stored_result_source_incomplete"


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


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_nullable_nested_fields_are_absent_and_falsy_values_are_preserved(blank) -> None:
    schema = {"type": "object", "required": ["name", "count", "enabled", "rows"], "properties": {
        "name": {"type": ["string", "null"], "minLength": 1},
        "optional": {"type": "integer"}, "count": {"type": "integer"},
        "enabled": {"type": "boolean"}, "rows": {"type": "array"},
    }}
    value = {"name": blank, "optional": blank, "count": 0, "enabled": False, "rows": []}
    result = _reduce(_request(expected_outputs=[TaskOutputSpec(key="value", description="Value", schema=schema)]),
                     _declaration(outputs={"value": {"kind": "value", "value": value}}))
    assert result.outcome is TaskOutcome.COMPLETED
    assert result.outputs["value"] == {"name": None, "count": 0, "enabled": False, "rows": []}


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_required_nonblank_output_is_never_invented(blank) -> None:
    result = _reduce(_request(expected_outputs=[TaskOutputSpec(key="value", description="Value", schema={"type": "string", "minLength": 1})]),
                     _declaration(outputs={"value": {"kind": "value", "value": blank}}))
    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.output_states["value"]["errors"][0]["keyword"] in {"type", "minLength"}


def test_optional_blank_output_is_omitted_when_schema_has_no_absent_form() -> None:
    request = _request(expected_outputs=[TaskOutputSpec(key="count", description="Count", required=False, schema={"type": "integer"})])
    result = _reduce(request, _declaration(outputs={"count": {"kind": "value", "value": ""}}))
    assert result.outcome is TaskOutcome.COMPLETED
    assert result.outputs == {}
    assert result.output_states["count"]["status"] == "missing"


def test_absence_normalization_resolves_refs_and_validates_union_constraints() -> None:
    from app.runtime.task_value_normalization import normalize_task_value
    schema = {"$defs": {"text": {"type": ["string", "null"], "minLength": 2}},
              "type": "object", "required": ["items"], "properties": {
                  "items": {"type": "array", "items": {"$ref": "#/$defs/text"}},
                  "text": {"anyOf": [{"type": "null"}, {"type": "string", "minLength": 2}]},
              }}
    normalized, changed = normalize_task_value({"items": ["", "ab"], "text": "  "}, schema)
    assert changed
    assert normalized == {"items": [None, "ab"], "text": None}
    assert TaskAttemptResultReducer._matches_schema(normalized, schema)
    assert normalize_task_value(normalized, schema) == (normalized, False)


@pytest.mark.parametrize("sql_inline", [True, False])
def test_sql_proof_accepts_reshaped_outputs_and_ignores_unrelated_clipped_sources(sql_inline) -> None:
    declaration = _declaration(outputs={"rows": {"kind": "value", "value": [{"models": ["a", "b"]}, {"models": ["c"]}]}},
                              coverage=[{"output_key": "rows", "output_path": None, "result_id": "sql", "query_call_ids": ["query"]}])
    receipts = [
        {"result_id": "unrelated", "inline_complete": False, "source_complete": False},
        {"result_id": "original", "inline_complete": False, "source_complete": True},
        {"result_id": "sql", "call_id": "query", "inline_complete": sql_inline, "analysis": {
            "mode": "sql", "result_id": "sql", "source_result_ids": ["original"],
            "row_count": 1, "query_result_stored": True, "query_complete": True, "source_complete": True,
        }},
    ]
    result = _reduce(_request(expected_outputs=[TaskOutputSpec(key="rows", description="Rows", schema={"type": "array"})]), declaration, {"receipts": receipts})
    assert result.outcome is TaskOutcome.COMPLETED


def test_sql_completeness_is_explicit_in_output_contract() -> None:
    declaration = _declaration(outputs={"rows": {"kind": "value", "value": [1]}},
                              coverage=[{"output_key": "rows", "result_id": "sql", "query_call_ids": ["query"]}])
    verified = {"receipts": [{"result_id": "sql", "call_id": "query", "inline_complete": True, "analysis": {
        "mode": "sql", "result_id": "sql", "query_result_stored": True,
        "query_complete": True, "source_complete": False,
    }}]}
    spec = TaskOutputSpec(key="rows", description="Rows", schema={"type": "array"})
    assert _reduce(_request(expected_outputs=[spec]), declaration, verified).outcome is TaskOutcome.COMPLETED
    spec.require_complete_source = True
    assert _reduce(_request(expected_outputs=[spec]), declaration, verified).output_states["rows"]["reason"] == "stored_result_source_incomplete"


def test_sql_proof_rejects_unobserved_refs_and_incomplete_query() -> None:
    request = _request(expected_outputs=[TaskOutputSpec(key="rows", description="Rows", schema={"type": "array"})])
    declaration = _declaration(outputs={"rows": {"kind": "value", "value": [1]}},
                              coverage=[{"output_key": "rows", "result_id": "sql", "query_call_ids": ["query"]}])
    assert _reduce(request, declaration).output_states["rows"]["reason"] == "stored_result_array_coverage_unverified"
    verified = {"receipts": [{"result_id": "sql", "call_id": "query", "analysis": {
        "mode": "sql", "result_id": "sql", "query_result_stored": True,
        "query_complete": False, "source_complete": True,
    }}]}
    assert _reduce(request, declaration, verified).output_states["rows"]["reason"] == "stored_result_query_incomplete"


def test_select_proof_still_requires_contiguous_complete_pages() -> None:
    request = _request(expected_outputs=[TaskOutputSpec(key="rows", description="Rows", schema={"type": "array"})])
    declaration = _declaration(outputs={"rows": {"kind": "value", "value": [1, 2]}},
                              coverage=[{"output_key": "rows", "result_id": "original", "query_call_ids": ["page1", "page2"]}])
    pages = [{"call_id": f"page{index + 1}", "analysis": {
        "mode": "select", "source_result_id": "original", "selection_id": "selection",
        "offset": index, "returned_count": 1, "matched_count": 2, "complete": index == 1,
    }} for index in range(2)]
    assert _reduce(request, declaration, {"receipts": pages}).outcome is TaskOutcome.COMPLETED
    pages[1]["analysis"]["offset"] = 2
    assert _reduce(request, declaration, {"receipts": pages}).output_states["rows"]["reason"] == "stored_result_page_gap"


def test_legacy_source_claim_is_linked_to_sql_result_by_runtime_provenance() -> None:
    declaration = _declaration(outputs={"rows": {"kind": "value", "value": [1, 2]}}, coverage=[{
        "output_key": "rows", "result_id": "source", "query_call_ids": ["source-call", "query"],
    }])
    verified = {"receipts": [
        {"result_id": "source", "call_id": "source-call", "inline_complete": False},
        {"result_id": "query-result", "call_id": "query", "inline_complete": True, "analysis": {
            "mode": "sql", "result_id": "query-result", "source_result_ids": ["source"],
            "row_count": 1, "query_result_stored": True, "source_complete": True,
        }},
    ]}
    request = _request(expected_outputs=[TaskOutputSpec(key="rows", description="Rows", schema={"type": "array"})])
    assert _reduce(request, declaration, verified).outcome is TaskOutcome.COMPLETED
    verified["receipts"][1]["analysis"]["source_result_ids"] = ["another-source"]
    assert _reduce(request, declaration, verified).outcome is TaskOutcome.UNFULFILLABLE


@pytest.mark.parametrize("value", [0, False, [], {}])
def test_falsy_values_are_not_absence(value) -> None:
    from app.runtime.task_value_normalization import normalize_task_value
    assert normalize_task_value(value, {}) == (value, False)
