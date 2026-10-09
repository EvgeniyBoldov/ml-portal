"""Accept the task protocol; data schemas are advisory to LLM consumers."""
from __future__ import annotations

from itertools import islice
from typing import Any, Dict

from app.runtime.orchestrator_contracts import (
    AgentExecutionCompletion, TaskOutcome, TaskRequest, TaskResult,
    TaskCompletionDeclaration, TaskOutputFulfillment,
)


def schema_diagnostics(value: Any, schema: Dict[str, Any], path: str) -> list[dict[str, Any]]:
    if not schema:
        return []
    from jsonschema import Draft202012Validator
    from referencing import Registry
    try:
        Draft202012Validator.check_schema(schema)
        return [{"code": "schema_deviation", "path": path,
                 "message": error.message[:1000], "severity": "warning"}
                for error in islice(Draft202012Validator(schema, registry=Registry()).iter_errors(value), 10)]
    except Exception:
        return [{"code": "advisory_schema_invalid", "path": path, "severity": "warning",
                 "message": "Requested schema cannot be used; actual data is preserved."}]


class TaskAttemptResultReducer:
    def reduce(self, *, request: TaskRequest, declaration: TaskCompletionDeclaration,
               verified: Dict[str, Any]) -> TaskResult:
        data = declaration.structured_response
        outputs = dict(data) if isinstance(data, dict) else ({"structured_response": data}
                   if "structured_response" in declaration.model_fields_set else {})
        attachments = [dict(item) for item in verified.get("artifacts") or []
                       if isinstance(item, dict) and item.get("artifact_id") and not item.get("deleted")]
        diagnostics = schema_diagnostics(data, request.response_spec.json_schema, "structured_response")
        states = {}
        for spec in request.expected_outputs:
            if spec.fulfillment == TaskOutputFulfillment.TASK_RESULT:
                value = outputs.get(spec.key)
                diagnostics.extend(schema_diagnostics(value, spec.json_schema, f"structured_response/{spec.key}"))
                states[spec.key] = {"status": "available" if spec.key in outputs else "missing",
                                    "fulfillment": "task_result"}
            elif spec.fulfillment == TaskOutputFulfillment.ARTIFACT:
                states[spec.key] = {"status": "fulfilled" if attachments else "missing", "fulfillment": "artifact"}
        outcome = {AgentExecutionCompletion.FULFILLED: TaskOutcome.COMPLETED,
                   AgentExecutionCompletion.NEEDS: TaskOutcome.NEEDS_DEPENDENCY,
                   AgentExecutionCompletion.UNFULFILLABLE: TaskOutcome.UNFULFILLABLE}[declaration.completion_claim]
        file_required = request.response_spec.mode == "artifact" or any(
            spec.required and spec.fulfillment == TaskOutputFulfillment.ARTIFACT for spec in request.expected_outputs)
        reason = None
        limitation = declaration.limitation
        if outcome == TaskOutcome.COMPLETED and file_required and not attachments:
            outcome, reason = TaskOutcome.UNFULFILLABLE, "required_artifact_missing"
            limitation = {"code": reason, "message": "The requested attachment was not created.", "action": "none"}
        return TaskResult(outcome=outcome, completion=declaration.completion_claim,
                          description=declaration.report, answer=declaration.answer,
                          structured_response=data, outputs=outputs, output_states=states,
                          needs=declaration.needs, attachments=attachments,
                          sources=[dict(item) for item in verified.get("sources") or [] if isinstance(item, dict)],
                          diagnostics=diagnostics, reason_code=reason, limitation=limitation, verified=verified)
