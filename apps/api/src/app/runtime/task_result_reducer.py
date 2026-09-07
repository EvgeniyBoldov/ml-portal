"""Runtime-owned reduction from an agent execution to a logical task result."""
from __future__ import annotations

from typing import Any, Dict

from app.runtime.orchestrator_contracts import (
    AgentExecutionCompletion,
    AgentExecutionResult,
    DiscoveredNeed,
    FreshnessPolicy,
    TaskOutputFulfillment,
    TaskOutputValue,
    TaskOutcome,
    TaskRequest,
    TaskResult,
)


class TaskAttemptResultReducer:
    """Validate task expectations without giving executors lifecycle authority."""

    def reduce(
        self,
        *,
        request: TaskRequest,
        execution: AgentExecutionResult,
        verified: Dict[str, Any] | None = None,
    ) -> TaskResult:
        verified = dict(verified if verified is not None else execution.verified)
        outputs, missing, invalid = self._fulfilled_outputs(request, execution, verified)
        if execution.completion == AgentExecutionCompletion.NEEDS:
            return TaskResult(
                outcome=TaskOutcome.NEEDS_DEPENDENCY,
                description=execution.description,
                outputs=outputs,
                needs=execution.needs,
                verified=verified,
            )
        if execution.completion == AgentExecutionCompletion.UNFULFILLABLE:
            return TaskResult(
                outcome=TaskOutcome.UNFULFILLABLE,
                description=execution.description,
                outputs=outputs,
                limitation=execution.limitation,
                verified=verified,
            )
        if request.freshness_policy == FreshnessPolicy.REQUIRE_RETRIEVAL and not verified.get("fresh_retrieval"):
            return TaskResult(
                outcome=TaskOutcome.NEEDS_DEPENDENCY,
                description=execution.description,
                outputs=outputs,
                needs=[DiscoveredNeed(
                    ref="fresh_retrieval",
                    key="fresh_retrieval",
                    kind="data",
                    description="A successful compatible retrieval is required for this task attempt.",
                )],
                reason_code="fresh_retrieval_missing",
                limitation={"code": "fresh_retrieval_missing", "message": "A fresh retrieval is required to complete this task.", "action": "retry_later"},
                verified=verified,
            )

        if invalid:
            return TaskResult(
                outcome=TaskOutcome.UNFULFILLABLE,
                description=execution.description,
                outputs=outputs,
                reason_code="output_schema_invalid",
                limitation={"code": "output_schema_invalid", "message": "The task result did not satisfy the required output format.", "action": "none"},
                verified=verified,
            )
        if missing:
            return TaskResult(
                outcome=TaskOutcome.UNFULFILLABLE,
                description=execution.description,
                outputs=outputs,
                reason_code="required_output_missing",
                limitation={"code": "required_output_missing", "message": "The task result did not include a required output.", "action": "none"},
                verified=verified,
            )
        return TaskResult(
            outcome=TaskOutcome.COMPLETED,
            description=execution.description,
            outputs=outputs,
            verified=verified,
        )

    @staticmethod
    def _fulfilled_outputs(
        request: TaskRequest,
        execution: AgentExecutionResult,
        verified: Dict[str, Any],
    ) -> tuple[Dict[str, TaskOutputValue], list[str], list[str]]:
        declared_keys = {spec.key for spec in request.expected_outputs}
        outputs = {
            key: value for key, value in execution.outputs.items()
            if key in declared_keys
        }
        missing: list[str] = []
        invalid: list[str] = []
        artifacts = list(verified.get("artifacts") or [])
        receipts = [item for item in verified.get("receipts") or [] if isinstance(item, dict)]
        for spec in request.expected_outputs:
            value = outputs.get(spec.key)
            if spec.fulfillment == TaskOutputFulfillment.ARTIFACT:
                # Artifact authority belongs to the runtime tool ledger.  An
                # LLM may describe the generated file but cannot claim an
                # artifact identifier in its terminal JSON.
                if artifacts:
                    value = TaskOutputValue(artifacts=artifacts)
                    outputs[spec.key] = value
                else:
                    value = None
                    outputs.pop(spec.key, None)
                if value is None or not value.artifacts:
                    if spec.required:
                        missing.append(spec.key)
                    continue
            elif spec.fulfillment == TaskOutputFulfillment.VERIFIED_RECEIPT:
                matching_receipts = [
                    receipt for receipt in receipts
                    if str(receipt.get("operation") or "") in spec.receipt_operations
                    or str(receipt.get("canonical_operation") or "") in spec.receipt_operations
                ]
                if value is None or not matching_receipts:
                    if spec.required:
                        missing.append(spec.key)
                    continue
            elif value is None and spec.required:
                missing.append(spec.key)
                continue
            if value is not None and spec.json_schema:
                payload = (
                    value.data
                    if value.data is not None
                    else value.text
                    if value.text is not None
                    else value.artifacts
                )
                if not TaskAttemptResultReducer._matches_schema(payload, spec.json_schema):
                    invalid.append(spec.key)
                    outputs.pop(spec.key, None)
                    continue
                outputs[spec.key] = value
        return outputs, missing, invalid

    @staticmethod
    def _matches_schema(value: Any, schema: Dict[str, Any]) -> bool:
        """Validate the planner-declared JSON Schema before accepting output."""
        try:
            import jsonschema

            jsonschema.Draft202012Validator(schema).validate(value)
            return True
        except ImportError:
            # A declared schema is a hard runtime contract. Running without
            # its validator must fail closed instead of accepting a subset.
            return False
        except Exception:
            return False
