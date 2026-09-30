"""Runtime-owned reduction of a typed task-completion declaration."""
from __future__ import annotations

from typing import Any, Dict

from app.runtime.orchestrator_contracts import (
    AgentExecutionCompletion, ArtifactOutputSlot, ArtifactSelection, DiscoveredNeed,
    EvidenceOutputSlot, EvidenceSelection, FreshnessPolicy, TaskCompletionDeclaration,
    TaskOutputFulfillment, TaskOutcome, TaskRequest, TaskResult, ValueOutputSlot,
)
from app.runtime.task_value_normalization import is_absent, normalize_task_value


class TaskAttemptResultReducer:
    """Verify every output slot exactly once and derive the task outcome.

    ``outputs`` is the direct-value projection used by bindings. ``output_states``
    is authoritative for value, receipt and artifact fulfillment alike.
    """

    def reduce(self, *, request: TaskRequest, declaration: TaskCompletionDeclaration, verified: Dict[str, Any]) -> TaskResult:
        outputs, states, invalid, missing, evidence, artifacts = self._verify_outputs(request, declaration, verified)
        if invalid:
            return self._unfulfillable(declaration, outputs, states, verified, evidence, artifacts, "output_contract_invalid", "Invalid task outputs: " + "; ".join(f"outputs.{key}: {states[key].get('reason', 'invalid')}" for key in invalid))
        if declaration.completion_claim == AgentExecutionCompletion.NEEDS:
            return TaskResult(outcome=TaskOutcome.NEEDS_DEPENDENCY, description=declaration.report, outputs=outputs, output_states=states, needs=declaration.needs, verified=verified, evidence_selections=evidence, artifact_selections=artifacts)
        if declaration.completion_claim == AgentExecutionCompletion.UNFULFILLABLE:
            return TaskResult(outcome=TaskOutcome.UNFULFILLABLE, description=declaration.report, outputs=outputs, output_states=states, limitation=declaration.limitation, verified=verified, evidence_selections=evidence, artifact_selections=artifacts)
        if request.freshness_policy == FreshnessPolicy.REQUIRE_RETRIEVAL and not verified.get("fresh_retrieval"):
            return self._unfulfillable(declaration, outputs, states, verified, evidence, artifacts, "fresh_retrieval_missing", "A fulfilled declaration requires a successful fresh retrieval receipt.")
        required_operations = self._required_retrieval_operations(request)
        observed_operations = {
            str(item.get("canonical_operation") or item.get("operation") or "")
            for item in verified.get("receipts") or []
            if isinstance(item, dict) and item.get("success") is not False
        }
        if required_operations and not required_operations.issubset(observed_operations):
            return self._unfulfillable(
                declaration, outputs, states, verified, evidence, artifacts,
                "required_retrieval_operation_missing",
                "A fulfilled declaration requires receipts from: " + ", ".join(sorted(required_operations)),
            )
        if missing:
            return self._unfulfillable(declaration, outputs, states, verified, evidence, artifacts, "required_output_missing", "The task result did not fulfill required outputs: " + ", ".join(missing))
        return TaskResult(outcome=TaskOutcome.COMPLETED, description=declaration.report, outputs=outputs, output_states=states, verified=verified, evidence_selections=evidence, artifact_selections=artifacts)

    @staticmethod
    def _required_retrieval_operations(request: TaskRequest) -> set[str]:
        """Bind well-known entity identifiers to their authoritative read."""
        inputs = request.inputs if isinstance(request.inputs, dict) else {}
        explicit = inputs.get("required_retrieval_operations")
        if isinstance(explicit, list):
            return {str(operation).strip() for operation in explicit if str(operation).strip()}
        if str(inputs.get("jira_task_id") or inputs.get("issue_key") or inputs.get("jira_key") or "").strip():
            return {"jira_get_issue"}
        return set()

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
        receipts: Dict[str, Dict[str, Any]] = {}
        for item in verified.get("receipts") or []:
            if not isinstance(item, dict) or item.get("success") is False:
                continue
            result_ref = str(item.get("result_ref") or "").strip()
            call_id = str(item.get("call_id") or "").strip()
            if result_ref:
                receipts[result_ref] = item
            # Follow-up tool context exposes evidence_call_id. Accept it as
            # an alias, but persist the canonical result_ref in selections.
            if call_id:
                receipts[call_id] = item
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
                value = slot.value if isinstance(slot, ValueOutputSlot) else None
                normalized_from_absence = False
                if isinstance(slot, ValueOutputSlot):
                    value, normalized_from_absence = self._coerce_absent_value(value, spec.json_schema)
                if not isinstance(slot, ValueOutputSlot) or (spec.json_schema and not self._matches_schema(value, spec.json_schema)):
                    if isinstance(slot, ValueOutputSlot) and not spec.required and is_absent(slot.value):
                        states[spec.key] = {"status": "missing", "fulfillment": "task_result", "normalized_from": "absence"}
                        continue
                    invalid.append(spec.key)
                    states[spec.key] = {"status": "invalid", "reason": "value_schema_invalid"}
                    if isinstance(slot, ValueOutputSlot):
                        states[spec.key]["errors"] = self._schema_errors(value, spec.json_schema)
                    continue
                outputs[spec.key] = value
                states[spec.key] = {"status": "fulfilled", "fulfillment": "task_result", "value_present": True}
                coverage_error = self._verify_output_coverage(
                    output_key=spec.key, value=value, declaration=declaration,
                    verified=verified, require_complete_source=spec.require_complete_source,
                )
                if coverage_error:
                    invalid.append(spec.key)
                    states[spec.key] = {"status": "invalid", "reason": coverage_error}
                    continue
                if normalized_from_absence:
                    states[spec.key]["normalized_from"] = "null" if slot.value is None else "absence"
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
                evidence_selections.extend(
                    EvidenceSelection(
                        result_ref=str(receipts[ref].get("result_ref") or ref),
                        output_keys=[spec.key],
                        description=spec.description,
                    )
                    for ref in slot.refs
                )
                states[spec.key] = {"status": "fulfilled", "fulfillment": "verified_receipt", "refs": slot.refs}
                continue
            if not isinstance(slot, ArtifactOutputSlot) or any(ref not in artifacts for ref in slot.refs):
                invalid.append(spec.key)
                states[spec.key] = {"status": "invalid", "reason": "artifact_not_verified", "refs": getattr(slot, "refs", [])}
                continue
            artifact_selections.extend(ArtifactSelection(artifact_ref=ref, output_key=spec.key, description=spec.description) for ref in slot.refs)
            states[spec.key] = {"status": "fulfilled", "fulfillment": "artifact", "refs": slot.refs}

        for key in sorted((set(declaration.outputs) | {claim.output_key for claim in declaration.coverage}) - known_keys):
            invalid.append(key)
            states[key] = {"status": "invalid", "reason": "unknown_output_key"}
        return outputs, states, invalid, missing, evidence_selections, artifact_selections

    @staticmethod
    def _verify_output_coverage(*, output_key: str, value: Any, declaration: TaskCompletionDeclaration,
                               verified: Dict[str, Any], require_complete_source: bool = False) -> str | None:
        """Verify observed provenance, keeping SQL transformations distinct from copies."""
        claims = [claim for claim in declaration.coverage if claim.output_key == output_key]
        receipts = [item for item in verified.get("receipts") or [] if isinstance(item, dict) and item.get("success") is not False]
        source_receipts = [item for item in receipts if item.get("result_id") and item.get("inline_complete") is False]
        by_call = {item.get("call_id"): item for item in receipts}

        def arrays(node: Any, prefix: str = "") -> list[tuple[str, list[Any]]]:
            found: list[tuple[str, list[Any]]] = []
            if isinstance(node, list):
                if node:
                    found.append((prefix, node))
                for index, child in enumerate(node):
                    found.extend(arrays(child, f"{prefix}.{index}" if prefix else str(index)))
            elif isinstance(node, dict):
                for key, child in node.items():
                    found.extend(arrays(child, f"{prefix}.{key}" if prefix else str(key)))
            return found

        def at_path(path: str) -> Any:
            node = value
            for part in path.split(".") if path else []:
                if isinstance(node, dict) and part in node:
                    node = node[part]
                elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
                    node = node[int(part)]
                else:
                    raise ValueError("coverage path does not exist")
            return node

        # A claim covers a whole subtree. SQL may aggregate or reshape rows,
        # so output array length is not evidence of SQL source completeness.
        for claim in claims:
            try:
                claimed_value = at_path(claim.output_path)
            except ValueError:
                return "stored_result_coverage_path_invalid"
            pages = []
            sql_results = []
            for call_id in claim.query_call_ids:
                page = by_call.get(call_id)
                analysis = page.get("analysis") if isinstance(page, dict) else None
                if isinstance(analysis, dict) and analysis.get("mode") == "sql":
                    # Accept the canonical SQL result ID, plus legacy source
                    # IDs only when runtime-recorded SQL provenance links them.
                    if not analysis.get("query_result_stored") or not (
                        analysis.get("result_id") == claim.result_id
                        or claim.result_id in (analysis.get("source_result_ids") or [])
                    ):
                        return "stored_result_array_coverage_unverified"
                    if analysis.get("query_complete") is False:
                        return "stored_result_query_incomplete"
                    if require_complete_source and analysis.get("source_complete") is not True:
                        return "stored_result_source_incomplete"
                    sql_results.append(analysis.get("result_id"))
                    continue
                if isinstance(page, dict) and not analysis and page.get("result_id") == claim.result_id:
                    # A source receipt may be included as additional evidence;
                    # it cannot replace an actual SQL/select receipt.
                    continue
                if (not isinstance(analysis, dict) or analysis.get("mode") != "select"
                        or analysis.get("source_result_id") != claim.result_id
                        or not analysis.get("selection_id")):
                    return "stored_result_array_coverage_unverified"
                pages.append(analysis)
            if sql_results:
                if pages or len(set(sql_results)) != 1:
                    return "stored_result_selection_mismatch"
                continue
            if not pages:
                return "stored_result_array_coverage_unverified"
            if require_complete_source and any(not page.get("source_complete") for page in pages):
                return "stored_result_source_incomplete"
            if not isinstance(claimed_value, list):
                return "stored_result_select_coverage_requires_array"
            selections = {page.get("selection_id") for page in pages}
            if len(selections) != 1:
                return "stored_result_selection_mismatch"
            pages.sort(key=lambda page: int(page.get("offset") or 0))
            expected_offset = 0
            for page in pages:
                if int(page.get("offset") or 0) != expected_offset:
                    return "stored_result_page_gap"
                expected_offset += int(page.get("returned_count") or 0)
            if (not pages[-1].get("complete")
                    or expected_offset != len(claimed_value)
                    or int(pages[0].get("matched_count") or 0) != len(claimed_value)):
                return "stored_result_array_incomplete"

        if require_complete_source and not claims:
            return "stored_result_complete_source_coverage_missing"
        if source_receipts:
            for path, _ in arrays(value):
                if not any(not claim.output_path or path == claim.output_path or path.startswith(claim.output_path + ".") for claim in claims):
                    return "stored_result_array_coverage_missing"
        return None

    @staticmethod
    def _matches_schema(value: Any, schema: Dict[str, Any]) -> bool:
        try:
            import jsonschema
            jsonschema.Draft202012Validator(schema).validate(value)
            return True
        except Exception:
            return False

    @staticmethod
    def _schema_errors(value: Any, schema: Dict[str, Any]) -> list[dict[str, str]]:
        from jsonschema import Draft202012Validator
        from referencing.exceptions import Unresolvable
        try:
            errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda error: str(list(error.absolute_path)))
        except Unresolvable:
            return [{"path": "", "keyword": "$ref", "message": "Task output schema contains an unresolved reference"}]
        return [{"path": "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in error.absolute_path),
                 "keyword": str(error.validator), "message": (
                     error.message if error.validator == "required" else
                     f"Expected {error.validator}={error.validator_value}" if error.validator in {"type", "minLength", "maxLength", "minItems", "maxItems", "minimum", "maximum"}
                     else "Value violates " + str(error.validator) + " constraint"
                 )}
                for error in errors[:10]]

    @classmethod
    def _coerce_absent_value(cls, value: Any, schema: Dict[str, Any]) -> tuple[Any, bool]:
        from referencing.exceptions import Unresolvable
        try:
            return normalize_task_value(value, schema)
        except Unresolvable:
            # An invalid schema reference must produce field feedback, not
            # terminate the agent loop before it can declare a limitation.
            return value, False
