"""Runtime-owned reduction from an agent execution to a logical task result."""
from __future__ import annotations

from typing import Any, Dict

from app.runtime.orchestrator_contracts import (
    AgentExecutionCompletion,
    AgentExecutionResult,
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
        if execution.completion == AgentExecutionCompletion.NEEDS:
            return TaskResult(
                outcome=TaskOutcome.NEEDS_DEPENDENCY,
                description=execution.description,
                outputs=dict(execution.outputs),
                partial_completion=execution.description,
                checkpoint=execution.checkpoint,
                needs=execution.needs,
                verified=verified,
            )
        if execution.completion == AgentExecutionCompletion.UNFULFILLABLE:
            return TaskResult(
                outcome=TaskOutcome.UNFULFILLABLE,
                description=execution.description,
                outputs=dict(execution.outputs),
                partial_completion=execution.description,
                checkpoint=execution.checkpoint,
                verified=verified,
            )
        if request.freshness_policy == FreshnessPolicy.REQUIRE_RETRIEVAL and not verified.get("fresh_retrieval"):
            return TaskResult(
                outcome=TaskOutcome.NEEDS_DEPENDENCY,
                description=execution.description,
                outputs=dict(execution.outputs),
                partial_completion=execution.description,
                checkpoint=execution.checkpoint,
                needs=[{
                    "ref": "fresh_retrieval",
                    "key": "fresh_retrieval",
                    "kind": "data",
                    "description": "A successful compatible retrieval is required for this task attempt.",
                }],
                reason_code="fresh_retrieval_missing",
                verified=verified,
            )

        outputs, missing, invalid = self._fulfilled_outputs(request, execution, verified)
        if invalid:
            return TaskResult(
                outcome=TaskOutcome.UNFULFILLABLE,
                description=execution.description,
                outputs=outputs,
                partial_completion=execution.description,
                checkpoint=execution.checkpoint,
                reason_code="output_schema_invalid",
                verified=verified,
            )
        if missing:
            return TaskResult(
                outcome=TaskOutcome.UNFULFILLABLE,
                description=execution.description,
                outputs=outputs,
                partial_completion=execution.description,
                checkpoint=execution.checkpoint,
                reason_code="required_output_missing",
                verified=verified,
            )
        return TaskResult(
            outcome=TaskOutcome.COMPLETED,
            description=execution.description,
            outputs=outputs,
            checkpoint=execution.checkpoint,
            verified=verified,
        )

    @staticmethod
    def _fulfilled_outputs(
        request: TaskRequest,
        execution: AgentExecutionResult,
        verified: Dict[str, Any],
    ) -> tuple[Dict[str, TaskOutputValue], list[str], list[str]]:
        outputs = dict(execution.outputs)
        missing: list[str] = []
        invalid: list[str] = []
        artifacts = list(verified.get("artifacts") or [])
        has_receipt = bool(verified.get("receipts"))
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
                if value is None or not has_receipt:
                    if spec.required:
                        missing.append(spec.key)
                    continue
            elif value is None and spec.required:
                missing.append(spec.key)
                continue
            if value is not None and spec.json_schema:
                payload = value.data if value.data is not None else value.model_dump(mode="json")
                if not TaskAttemptResultReducer._matches_schema(payload, spec.json_schema):
                    invalid.append(spec.key)
                outputs[spec.key] = value
        return outputs, missing, invalid

    @staticmethod
    def _matches_schema(value: Any, schema: Dict[str, Any]) -> bool:
        """Bounded validation for the task contract's common JSON Schema subset.

        Task output schemas are planner-facing shape hints, not a second
        arbitrary code execution surface.  Keep this deliberately small until
        the API image ships a shared JSON-schema validator.
        """
        expected_type = schema.get("type")
        type_matches = {
            "object": lambda item: isinstance(item, dict),
            "array": lambda item: isinstance(item, list),
            "string": lambda item: isinstance(item, str),
            "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "boolean": lambda item: isinstance(item, bool),
            "null": lambda item: item is None,
        }
        if isinstance(expected_type, str) and expected_type in type_matches and not type_matches[expected_type](value):
            return False
        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            return False
        if isinstance(value, dict):
            required = schema.get("required")
            if isinstance(required, list) and any(key not in value for key in required if isinstance(key, str)):
                return False
            properties = schema.get("properties")
            if isinstance(properties, dict):
                for key, child_schema in properties.items():
                    if key in value and isinstance(child_schema, dict) and not TaskAttemptResultReducer._matches_schema(value[key], child_schema):
                        return False
        if isinstance(value, list) and isinstance(schema.get("items"), dict):
            return all(TaskAttemptResultReducer._matches_schema(item, schema["items"]) for item in value)
        return True
