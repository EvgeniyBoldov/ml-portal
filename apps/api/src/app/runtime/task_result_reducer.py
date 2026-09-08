"""Runtime-owned verification of an agent's task-completion declaration."""
from __future__ import annotations

from typing import Any, Dict

from app.runtime.orchestrator_contracts import (
    AgentExecutionCompletion, TaskCompletionDeclaration, DiscoveredNeed,
    FreshnessPolicy, TaskOutputFulfillment, TaskOutcome, TaskRequest, TaskResult,
)


class TaskAttemptResultReducer:
    """The agent declares relevance; only runtime turns it into a task outcome."""

    def reduce(self, *, request: TaskRequest, declaration: TaskCompletionDeclaration, verified: Dict[str, Any]) -> TaskResult:
        outputs, missing, invalid = self._verify_outputs(request, declaration, verified)
        refs_error = self._verify_selections(request, declaration, verified)
        if declaration.completion_claim == AgentExecutionCompletion.NEEDS:
            return TaskResult(outcome=TaskOutcome.NEEDS_DEPENDENCY, description=declaration.report, outputs=outputs, needs=declaration.needs, verified=verified, evidence_selections=declaration.evidence_selections, artifact_selections=declaration.artifact_selections)
        if declaration.completion_claim == AgentExecutionCompletion.UNFULFILLABLE:
            return TaskResult(outcome=TaskOutcome.UNFULFILLABLE, description=declaration.report, outputs=outputs, limitation=declaration.limitation, verified=verified, evidence_selections=declaration.evidence_selections, artifact_selections=declaration.artifact_selections)
        if request.freshness_policy == FreshnessPolicy.REQUIRE_RETRIEVAL and not verified.get("fresh_retrieval"):
            return TaskResult(outcome=TaskOutcome.NEEDS_DEPENDENCY, description=declaration.report, outputs=outputs, needs=[DiscoveredNeed(ref="fresh_retrieval", key="fresh_retrieval", kind="data", description="A successful compatible retrieval is required for this task attempt.")], reason_code="fresh_retrieval_missing", verified=verified)
        if refs_error:
            return self._unfulfillable(declaration, outputs, verified, "selection_invalid", refs_error)
        if invalid:
            return self._unfulfillable(declaration, outputs, verified, "output_schema_invalid", "The task result did not satisfy the declared JSON Schema for: " + ", ".join(invalid))
        if missing:
            return self._unfulfillable(declaration, outputs, verified, "required_output_missing", "The task result did not include a required output.")
        return TaskResult(outcome=TaskOutcome.COMPLETED, description=declaration.report, outputs=outputs, verified=verified, evidence_selections=declaration.evidence_selections, artifact_selections=declaration.artifact_selections)

    @staticmethod
    def _unfulfillable(declaration: TaskCompletionDeclaration, outputs: Dict[str, Any], verified: Dict[str, Any], code: str, message: str) -> TaskResult:
        return TaskResult(outcome=TaskOutcome.UNFULFILLABLE, description=declaration.report, outputs=outputs, reason_code=code, limitation={"code": code, "message": message, "action": "none"}, verified=verified)

    def _verify_outputs(self, request: TaskRequest, declaration: TaskCompletionDeclaration, verified: Dict[str, Any]) -> tuple[Dict[str, Any], list[str], list[str]]:
        specs = {item.key: item for item in request.expected_outputs}
        outputs = {key: value for key, value in declaration.outputs.items() if key in specs}
        missing: list[str] = []
        invalid: list[str] = []
        selected_artifacts = {item.output_key for item in declaration.artifact_selections}
        selected_receipts = {item.result_ref for item in declaration.evidence_selections}
        receipt_by_ref = {str(item.get("result_ref") or item.get("call_id") or ""): item for item in verified.get("receipts") or [] if isinstance(item, dict)}
        for spec in request.expected_outputs:
            if spec.fulfillment == TaskOutputFulfillment.ARTIFACT:
                if spec.required and spec.key not in selected_artifacts:
                    missing.append(spec.key)
                continue
            if spec.fulfillment == TaskOutputFulfillment.VERIFIED_RECEIPT:
                matches = [receipt_by_ref[ref] for ref in selected_receipts if ref in receipt_by_ref and (str(receipt_by_ref[ref].get("operation") or "") in spec.receipt_operations or str(receipt_by_ref[ref].get("canonical_operation") or "") in spec.receipt_operations)]
                if spec.required and not matches:
                    missing.append(spec.key)
                continue
            value = outputs.get(spec.key)
            if value is None:
                if spec.required:
                    missing.append(spec.key)
                continue
            if spec.json_schema and not self._matches_schema(value, spec.json_schema):
                invalid.append(spec.key)
                outputs.pop(spec.key, None)
        return outputs, missing, invalid

    @staticmethod
    def _verify_selections(request: TaskRequest, declaration: TaskCompletionDeclaration, verified: Dict[str, Any]) -> str | None:
        known_outputs = {item.key for item in request.expected_outputs}
        receipt_refs = {str(item.get("result_ref") or item.get("call_id") or "") for item in verified.get("receipts") or [] if isinstance(item, dict)}
        artifact_refs = {str(item.get("artifact_ref") or item.get("artifact_id") or "") for item in verified.get("artifacts") or [] if isinstance(item, dict)}
        if any(ref and ref not in receipt_refs for ref in (item.result_ref for item in declaration.evidence_selections)):
            return "An evidence selection does not belong to this task attempt."
        if any(item.output_key not in known_outputs or item.artifact_ref not in artifact_refs for item in declaration.artifact_selections):
            return "An artifact selection is not a verified artifact for this task output."
        return None

    @staticmethod
    def _matches_schema(value: Any, schema: Dict[str, Any]) -> bool:
        try:
            import jsonschema
            jsonschema.Draft202012Validator(schema).validate(value)
            return True
        except Exception:
            return False
