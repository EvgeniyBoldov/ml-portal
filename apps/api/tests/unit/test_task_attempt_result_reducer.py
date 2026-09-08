from app.runtime.orchestrator_contracts import (
    ArtifactSelection, DiscoveredNeed, EvidenceSelection,
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
    result = _reduce(_request(expected_outputs=[TaskOutputSpec(key="answer", description="Answer")]), _declaration(outputs={"answer": "known fact"}))
    assert result.outcome is TaskOutcome.COMPLETED
    assert result.outputs["answer"] == "known fact"


def test_schema_validates_direct_output_value() -> None:
    result = _reduce(_request(expected_outputs=[TaskOutputSpec(key="tasks", description="Tasks", json_schema={"type": "array"})]), _declaration(outputs={"tasks": [{"key": "NIMS-3334"}]}))
    assert result.outcome is TaskOutcome.COMPLETED


def test_schema_rejects_wrong_direct_output_value() -> None:
    result = _reduce(_request(expected_outputs=[TaskOutputSpec(key="tasks", description="Tasks", json_schema={"type": "array"})]), _declaration(outputs={"tasks": {"items": []}}))
    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "output_schema_invalid"


def test_freshness_is_verified_by_runtime() -> None:
    result = _reduce(_request(freshness_policy="require_retrieval"), _declaration())
    assert result.outcome is TaskOutcome.NEEDS_DEPENDENCY
    assert result.reason_code == "fresh_retrieval_missing"


def test_needs_is_not_a_successful_task() -> None:
    declaration = TaskCompletionDeclaration(completion="needs", report="Need target", needs=[DiscoveredNeed(ref="target", key="target", description="Target")])
    assert _reduce(_request(), declaration).outcome is TaskOutcome.NEEDS_DEPENDENCY


def test_receipt_must_be_selected_and_verified() -> None:
    request = _request(expected_outputs=[TaskOutputSpec(key="policy", description="Policy", fulfillment=TaskOutputFulfillment.VERIFIED_RECEIPT, receipt_operations=["collection.document.search"])])
    declaration = _declaration(evidence_selections=[EvidenceSelection(result_ref="result_1", description="Policy source")])
    verified = {"receipts": [{"result_ref": "result_1", "canonical_operation": "collection.document.search"}]}
    assert _reduce(request, declaration, verified).outcome is TaskOutcome.COMPLETED


def test_artifact_must_be_selected_from_runtime_ledger() -> None:
    request = _request(expected_outputs=[TaskOutputSpec(key="report", description="Report", fulfillment=TaskOutputFulfillment.ARTIFACT)])
    declaration = _declaration(artifact_selections=[ArtifactSelection(artifact_ref="artifact-1", output_key="report", description="Generated report")])
    assert _reduce(request, declaration, {"artifacts": [{"artifact_ref": "artifact-1", "artifact_id": "artifact-1"}]}).outcome is TaskOutcome.COMPLETED


def test_unknown_artifact_selection_fails_task() -> None:
    request = _request(expected_outputs=[TaskOutputSpec(key="report", description="Report", fulfillment=TaskOutputFulfillment.ARTIFACT)])
    declaration = _declaration(artifact_selections=[ArtifactSelection(artifact_ref="invented", output_key="report", description="Nope")])
    result = _reduce(request, declaration)
    assert result.outcome is TaskOutcome.UNFULFILLABLE
    assert result.reason_code == "selection_invalid"
