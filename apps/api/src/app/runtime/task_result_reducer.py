"""Runtime-owned reduction of a typed task-completion declaration."""
from __future__ import annotations

from typing import Any, Dict

from app.runtime.orchestrator_contracts import (
    AgentExecutionCompletion, ArtifactOutputSlot, ArtifactSelection, DiscoveredNeed,
    EvidenceOutputSlot, EvidenceSelection, FreshnessPolicy, TaskCompletionDeclaration,
    TaskOutputFulfillment, TaskOutcome, TaskRequest, TaskResult, ValueOutputSlot,
)


class TaskAttemptResultReducer:
    """Verify every output slot exactly once and derive the task outcome.

    ``outputs`` is the direct-value projection used by bindings. ``output_states``
    is authoritative for value, receipt and artifact fulfillment alike.
    """

    def reduce(self, *, request: TaskRequest, declaration: TaskCompletionDeclaration, verified: Dict[str, Any]) -> TaskResult:
        outputs, states, invalid, missing, evidence, artifacts = self._verify_outputs(request, declaration, verified)
        if declaration.completion_claim == AgentExecutionCompletion.NEEDS:
            return TaskResult(outcome=TaskOutcome.NEEDS_DEPENDENCY, description=declaration.report, outputs=outputs, output_states=states, needs=declaration.needs, verified=verified, evidence_selections=evidence, artifact_selections=artifacts)
        if declaration.completion_claim == AgentExecutionCompletion.UNFULFILLABLE:
            return TaskResult(outcome=TaskOutcome.UNFULFILLABLE, description=declaration.report, outputs=outputs, output_states=states, limitation=declaration.limitation, verified=verified, evidence_selections=evidence, artifact_selections=artifacts)
        if request.freshness_policy == FreshnessPolicy.REQUIRE_RETRIEVAL and not verified.get("fresh_retrieval"):
            return TaskResult(outcome=TaskOutcome.NEEDS_DEPENDENCY, description=declaration.report, outputs=outputs, output_states=states, needs=[DiscoveredNeed(ref="fresh_retrieval", key="fresh_retrieval", kind="data", description="A successful compatible retrieval is required for this task attempt.")], reason_code="fresh_retrieval_missing", verified=verified, evidence_selections=evidence, artifact_selections=artifacts)
        if invalid:
            return self._unfulfillable(declaration, outputs, states, verified, evidence, artifacts, "output_contract_invalid", "Invalid task output slots: " + ", ".join(invalid))
        if missing:
            return self._unfulfillable(declaration, outputs, states, verified, evidence, artifacts, "required_output_missing", "The task result did not fulfill required outputs: " + ", ".join(missing))
        return TaskResult(outcome=TaskOutcome.COMPLETED, description=declaration.report, outputs=outputs, output_states=states, verified=verified, evidence_selections=evidence, artifact_selections=artifacts)

    @staticmethod
    def _unfulfillable(declaration: TaskCompletionDeclaration, outputs: Dict[str, Any], states: Dict[str, Dict[str, Any]], verified: Dict[str, Any], evidence: list[EvidenceSelection], artifacts: list[ArtifactSelection], code: str, message: str) -> TaskResult:
        return TaskResult(outcome=TaskOutcome.UNFULFILLABLE, description=declaration.report, outputs=outputs, output_states=states, reason_code=code, limitation={"code": code, "message": message, "action": "none"}, verified=verified, evidence_selections=evidence, artifact_selections=artifacts)

    def _verify_outputs(self, request: TaskRequest, declaration: TaskCompletionDeclaration, verified: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Dict[str, Any]], list[str], list[str], list[EvidenceSelection], list[ArtifactSelection]]:
        outputs: Dict[str, Any] = {}
        states: Dict[str, Dict[str, Any]] = {}
        invalid: list[str] = []
        missing: list[str] = []
        evidence_selections: list[EvidenceSelection] = []
        artifact_selections: list[ArtifactSelection] = []
        receipts = {str(item.get("result_ref") or item.get("call_id") or ""): item for item in verified.get("receipts") or [] if isinstance(item, dict)}
        artifacts = {str(item.get("artifact_ref") or item.get("artifact_id") or ""): item for item in verified.get("artifacts") or [] if isinstance(item, dict)}
        known_keys = {spec.key for spec in request.expected_outputs}

        for spec in request.expected_outputs:
            # Presence is intentionally distinct from a present JSON null.
            if spec.key not in declaration.outputs:
                states[spec.key] = {"status": "missing", "fulfillment": spec.fulfillment.value}
                if spec.required:
                    missing.append(spec.key)
                continue
            slot = declaration.outputs[spec.key]
            if spec.fulfillment == TaskOutputFulfillment.TASK_RESULT:
                if not isinstance(slot, ValueOutputSlot) or (spec.json_schema and not self._matches_schema(slot.value, spec.json_schema)):
                    invalid.append(spec.key)
                    states[spec.key] = {"status": "invalid", "reason": "value_schema_invalid"}
                    continue
                outputs[spec.key] = slot.value
                states[spec.key] = {"status": "fulfilled", "fulfillment": "task_result", "value_present": True}
                continue
            if spec.fulfillment == TaskOutputFulfillment.VERIFIED_RECEIPT:
                if not isinstance(slot, EvidenceOutputSlot):
                    invalid.append(spec.key)
                    states[spec.key] = {"status": "invalid", "reason": "expected_evidence_slot"}
                    continue
                matches = [receipts[ref] for ref in slot.refs if ref in receipts and (str(receipts[ref].get("operation") or "") in spec.receipt_operations or str(receipts[ref].get("canonical_operation") or "") in spec.receipt_operations)]
                if len(matches) != len(slot.refs) or not matches:
                    invalid.append(spec.key)
                    states[spec.key] = {"status": "invalid", "reason": "receipt_not_verified", "refs": slot.refs}
                    continue
                evidence_selections.extend(EvidenceSelection(result_ref=ref, output_keys=[spec.key], description=spec.description) for ref in slot.refs)
                states[spec.key] = {"status": "fulfilled", "fulfillment": "verified_receipt", "refs": slot.refs}
                continue
            if not isinstance(slot, ArtifactOutputSlot) or any(ref not in artifacts for ref in slot.refs):
                invalid.append(spec.key)
                states[spec.key] = {"status": "invalid", "reason": "artifact_not_verified", "refs": getattr(slot, "refs", [])}
                continue
            artifact_selections.extend(ArtifactSelection(artifact_ref=ref, output_key=spec.key, description=spec.description) for ref in slot.refs)
            states[spec.key] = {"status": "fulfilled", "fulfillment": "artifact", "refs": slot.refs}

        invalid.extend(sorted(set(declaration.outputs) - known_keys))
        return outputs, states, invalid, missing, evidence_selections, artifact_selections

    @staticmethod
    def _matches_schema(value: Any, schema: Dict[str, Any]) -> bool:
        try:
            import jsonschema
            jsonschema.Draft202012Validator(schema).validate(value)
            return True
        except Exception:
            return False
