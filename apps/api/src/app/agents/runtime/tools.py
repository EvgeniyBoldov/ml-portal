"""Runtime tool execution with validation, timeouts, and confirmation gates."""
from __future__ import annotations

import asyncio
import ast
import copy
import json
import os
from typing import Any, Dict, List, Optional, Tuple


try:
    import jsonschema as _jsonschema
except ImportError:
    _jsonschema = None  # type: ignore[assignment]

_JSONSCHEMA_FORCE_DISABLE = os.getenv("RUNTIME_DISABLE_JSONSCHEMA", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_JSONSCHEMA_AVAILABLE = (_jsonschema is not None) and not _JSONSCHEMA_FORCE_DISABLE

from app.agents.context import ToolCall, ToolContext, ToolResult
from app.agents.contracts import ResolvedOperation
from app.agents.runtime.confirmation import (
    ConfirmationService,
    build_operation_fingerprint,
    get_confirmation_service,
)
from app.agents.runtime.prompt_contract import build_prompt_input_schema
from app.agents.runtime.result_context import ModelResultView, ResultNextAction, ResultUnavailable, SourceCoverage
from app.agents.runtime.tool_reuse_policy import ToolCallReusePolicy
from app.core.logging import get_logger
from app.runtime.error_payloads import build_debug_payload, build_error_metadata
from app.runtime.operation_errors import (
    OperationExecutionError,
    OperationValidationError,
    RuntimeErrorCode,
)

logger = get_logger(__name__)


# Tool results are stored separately; this bounds only prompt projections.
MAX_COLLECTION_INFO_TEXT_CHARS = 320
MAX_COLLECTION_INFO_RULES_CHARS = 1_200
MAX_TEMPLATE_SEARCH_HITS = 8
MAX_TEMPLATE_SEARCH_TITLE_CHARS = 240
MAX_TEMPLATE_SEARCH_FRAGMENT_CHARS = 320


class ConfirmationRequiredError(RuntimeError):
    def __init__(self, payload: Dict[str, Any]) -> None:
        super().__init__(str(payload.get("summary") or "Operation requires confirmation"))
        self.payload = payload


class OperationExecutionFacade:
    """Execute tool calls with validation, timeouts, and source extraction."""
    def __init__(
        self,
        confirmation_service: Optional[ConfirmationService] = None,
        reuse_policy: Optional[ToolCallReusePolicy] = None,
    ) -> None:
        self._confirmation_service = confirmation_service or get_confirmation_service()
        self._reuse_policy = reuse_policy or ToolCallReusePolicy()

    async def execute(
        self,
        operation_call: ToolCall,
        ctx: ToolContext,
        operations: List[ResolvedOperation],
        timeout_s: Optional[float] = None,
    ) -> Tuple[ToolResult, List[dict]]:
        """Execute a single operation call.

        Returns:
            Tuple of (ToolResult, sources list for RAG-like tools)

        Bounded tool diagnostics (from ToolExecutionNotes) are attached to
        result.metadata["logs"] and become part of the canonical tool result.
        """
        operation, resolved_slug_error = self._find_operation(
            operation_call.tool_name,
            operation_call.arguments,
            operations,
        )

        if not operation:
            logger.error(f"Tool not found: {operation_call.tool_name}")
            message = resolved_slug_error or f"Tool '{operation_call.tool_name}' not found"
            code = (
                RuntimeErrorCode.OPERATION_AMBIGUOUS
                if resolved_slug_error and "ambiguous" in resolved_slug_error.lower()
                else RuntimeErrorCode.OPERATION_UNAVAILABLE
            )
            err = OperationExecutionError(
                code=code,
                message=message,
                retryable=False,
            )
            return ToolResult.fail(message, **err.to_metadata()), []

        if operation.operation_slug != operation_call.tool_name:
            logger.info(
                "Resolved shorthand tool '%s' -> '%s'",
                operation_call.tool_name,
                operation.operation_slug,
            )
            operation_call = ToolCall(
                id=operation_call.id,
                tool_name=operation.operation_slug,
                arguments=operation_call.arguments,
            )

        normalized_arguments = self._normalize_args(operation, operation_call.arguments)
        if normalized_arguments is not operation_call.arguments:
            operation_call = ToolCall(
                id=operation_call.id,
                tool_name=operation_call.tool_name,
                arguments=normalized_arguments,
            )

        validation_error = self._validate_args(operation, operation_call.arguments)
        if validation_error:
            logger.warning(
                "Operation args validation failed: %s (%s)",
                validation_error.message,
                validation_error.field_path or "root",
            )
            user_message = validation_error.to_user_message()
            return ToolResult.fail(
                user_message,
                **{
                    **validation_error.to_metadata(),
                    "user_message": user_message,
                    "operator_message": validation_error.message,
                    "source": "tool",
                    "debug": build_debug_payload(
                        context={"field_path": validation_error.field_path} if validation_error.field_path else None,
                    ),
                },
            ), []

        from app.agents.runtime.result_workspace_tools import WORKSPACE_TOOLS, execute_workspace
        if operation_call.tool_name in WORKSPACE_TOOLS:
            try:
                execution = execute_workspace(operation_call, ctx, self, operations, timeout_s)
                result = await asyncio.wait_for(execution, timeout=timeout_s) if timeout_s is not None else await execution
                return result, []
            except asyncio.TimeoutError:
                message = f"Execution timed out after {timeout_s} seconds"
                logger.error("Workspace tool %s timed out after %ss", operation_call.tool_name, timeout_s)
                return ToolResult.fail(message, **build_error_metadata(
                    error_code=RuntimeErrorCode.OPERATION_TIMEOUT.value,
                    retryable=True, user_message=message, operator_message=message,
                    source="tool")), []

        target = operation.target
        target_identity = ":".join(str(value or "") for value in (
            operation.operation_slug,
            getattr(target, "provider_instance_id", None),
            getattr(target, "data_instance_id", None),
            getattr(target, "provider_url", None),
            getattr(target, "mcp_tool_name", None),
        ))
        ledger = ctx.extra.get("runtime_execution_tool_ledger") or ctx.extra.get("runtime_tool_ledger")
        execution_id = str(
            ctx.extra.get("runtime_agent_execution_id") or ctx.extra.get("lifecycle_agent_execution_id") or ""
        ) or None
        if ledger is not None and hasattr(ledger, "set_call_target"):
            if ctx.extra.get("runtime_execution_tool_ledger") is ledger and hasattr(ledger, "entries"):
                has_call = any(entry.call_id == operation_call.id for entry in ledger.entries)
                if not has_call and hasattr(ledger, "register_call"):
                    ledger.register_call(
                        operation=operation_call.tool_name,
                        call_id=operation_call.id,
                        arguments=operation_call.arguments or {},
                        iteration=int(ctx.extra.get("runtime_iteration") or 0),
                        agent_slug=str(ctx.extra.get("agent_slug") or "") or None,
                        phase_id=None,
                        operation_side_effects=operation.side_effects,
                        risk_level=operation.risk_level,
                    )
            ledger.set_call_target(call_id=operation_call.id, target_identity=target_identity,
                                   arguments=operation_call.arguments,
                                   execution_id=execution_id,
                                   operation_side_effects=operation.side_effects,
                                   risk_level=operation.risk_level)

        previous_identity = ctx.extra.get("runtime_tool_target_identity")
        previous_active_id = ctx.extra.get("runtime_active_tool_call_id")
        ctx.extra["runtime_tool_target_identity"] = target_identity
        ctx.extra["runtime_active_tool_call_id"] = operation_call.id
        try:
            reused = self._reuse_policy.maybe_reuse(
                operation_slug=operation_call.tool_name,
                arguments=operation_call.arguments,
                ctx=ctx,
            )
        finally:
            if previous_identity is None:
                ctx.extra.pop("runtime_tool_target_identity", None)
            else:
                ctx.extra["runtime_tool_target_identity"] = previous_identity
            if previous_active_id is None:
                ctx.extra.pop("runtime_active_tool_call_id", None)
            else:
                ctx.extra["runtime_active_tool_call_id"] = previous_active_id
        if reused is not None:
            result, sources = reused
            logger.info(
                "Reused tool result for tool '%s' from in-turn ledger",
                operation_call.tool_name,
            )
            return result, sources

        await self._ensure_confirmation_if_required(
            operation=operation,
            operation_call=operation_call,
            ctx=ctx,
        )

        try:
            dispatched = False
            logger.info(f"Executing tool: {operation_call.tool_name}")
            executor = ctx.get_runtime_deps().operation_executor
            if not executor:
                err = OperationExecutionError(
                    code=RuntimeErrorCode.OPERATION_EXECUTION_FAILED,
                    message="Operation executor is not configured",
                    retryable=False,
                )
                return ToolResult.fail(
                    err.message,
                    **build_error_metadata(
                        error_code=err.code.value,
                        retryable=err.retryable,
                        user_message=err.message,
                        operator_message=err.message,
                        source="tool",
                        debug=build_debug_payload(
                            context={"tool": operation_call.tool_name, "reason": "executor_missing"},
                        ),
                    ),
                ), []

            previous_call_id = ctx.extra.get("runtime_active_tool_call_id")
            previous_tool_slug = ctx.extra.get("runtime_active_tool_slug")
            previous_timeout = ctx.extra.get("runtime_operation_timeout_s")
            ctx.extra["runtime_active_tool_call_id"] = operation_call.id
            ctx.extra["runtime_active_tool_slug"] = operation_call.tool_name
            if timeout_s is not None:
                ctx.extra["runtime_operation_timeout_s"] = timeout_s
            try:
                dispatched = True
                if timeout_s is not None:
                    result = await asyncio.wait_for(
                        executor.execute(operation_call, ctx), timeout=timeout_s,
                    )
                else:
                    result = await executor.execute(operation_call, ctx)
            finally:
                if previous_call_id is None:
                    ctx.extra.pop("runtime_active_tool_call_id", None)
                else:
                    ctx.extra["runtime_active_tool_call_id"] = previous_call_id
                if previous_tool_slug is None:
                    ctx.extra.pop("runtime_active_tool_slug", None)
                else:
                    ctx.extra["runtime_active_tool_slug"] = previous_tool_slug
                if previous_timeout is None:
                    ctx.extra.pop("runtime_operation_timeout_s", None)
                else:
                    ctx.extra["runtime_operation_timeout_s"] = previous_timeout

            sources: List[dict] = []
            if result.success and result.metadata.get("sources"):
                sources = result.metadata["sources"]

            tool_logs = result.metadata.get("logs")
            if tool_logs:
                warning_count = len(
                    [e for e in tool_logs if e.get("level") in ("warning", "error")],
                )
                if warning_count:
                    logger.warning(
                        f"Tool '{operation_call.tool_name}' produced "
                        f"{warning_count} warnings/errors",
                    )

            if not result.success and dispatched and operation.side_effects:
                failure = result.metadata.get("mcp_failure")
                category = failure.get("category") if isinstance(failure, dict) else None
                kind = failure.get("kind") if isinstance(failure, dict) else None
                error_code = result.metadata.get("error_code")
                if (error_code in {RuntimeErrorCode.OPERATION_TIMEOUT.value,
                                   RuntimeErrorCode.OPERATION_EXECUTION_FAILED.value,
                                   "transport_error", "tool_outcome_unknown"}
                        or category in {"availability", "unknown"}
                        or kind in {"transport", "http", "protocol"}):
                    result.metadata.update(outcome_unknown=True, error_code="tool_outcome_unknown", retryable=False)
            return result, sources

        except asyncio.TimeoutError:
            logger.error(
                f"Tool {operation_call.tool_name} timed out after {timeout_s}s",
            )
            outcome_unknown = bool(dispatched and operation.side_effects)
            err = OperationExecutionError(
                code=RuntimeErrorCode.OPERATION_TIMEOUT,
                message=f"Execution timed out after {timeout_s} seconds",
                retryable=not outcome_unknown,
            )
            return ToolResult.fail(
                err.message,
                **build_error_metadata(
                    error_code="tool_outcome_unknown" if outcome_unknown else err.code.value,
                    retryable=err.retryable,
                    user_message=err.message,
                    operator_message=err.message,
                    source="tool",
                    debug=build_debug_payload(
                        context={"tool": operation_call.tool_name, "timeout_seconds": timeout_s},
                    ),
                ),
                **({"outcome_unknown": True} if outcome_unknown else {}),
            ), []

        except Exception as e:
            logger.error(
                f"Tool {operation_call.tool_name} execution failed: {e}",
                exc_info=True,
            )
            outcome_unknown = bool(dispatched and operation.side_effects)
            err = OperationExecutionError(
                code=RuntimeErrorCode.OPERATION_EXECUTION_FAILED,
                message=str(e),
                retryable=not outcome_unknown,
            )
            return ToolResult.fail(
                err.message,
                **build_error_metadata(
                    error_code="tool_outcome_unknown" if outcome_unknown else err.code.value,
                    retryable=err.retryable,
                    user_message=err.message,
                    operator_message=str(e),
                    source="tool",
                    debug=build_debug_payload(
                        exc=e,
                        context={"tool": operation_call.tool_name},
                    ),
                ),
                **({"outcome_unknown": True} if outcome_unknown else {}),
            ), []

    async def _ensure_confirmation_if_required(
        self,
        *,
        operation: ResolvedOperation,
        operation_call: ToolCall,
        ctx: ToolContext,
    ) -> None:
        if not bool(operation.requires_confirmation):
            return
        fingerprint = build_operation_fingerprint(
            tool_slug=operation.operation_slug,
            operation=operation.operation,
            args=operation_call.arguments or {},
        )
        if ctx.chat_id is None:
            # This compatibility path is for non-chat callers that cannot
            # issue a signed confirmation token. Chat and sandbox continuations
            # always use the signed-token path below.
            approved = ctx.extra.get("sandbox_confirmed_fingerprints")
            approved_list = approved if isinstance(approved, list) else []
            if fingerprint in approved_list:
                return
            args_preview = json.dumps(
                operation_call.arguments or {},
                ensure_ascii=False,
                default=str,
            )[:600]
            raise ConfirmationRequiredError(
                payload={
                    "operation_fingerprint": fingerprint,
                    "tool_slug": operation.operation_slug,
                    "operation": operation.operation,
                    "risk_level": operation.risk_level,
                    "args_preview": args_preview,
                    "summary": operation.description or "Operation requires explicit confirmation",
                }
            )
        raw_tokens = ctx.extra.get("confirmation_tokens")
        tokens = raw_tokens if isinstance(raw_tokens, list) else []

        for token in tokens:
            if not isinstance(token, str) or not token.strip():
                continue
            if await asyncio.to_thread(self._confirmation_service.verify,
                token=token,
                user_id=ctx.user_id,
                chat_id=ctx.chat_id,
                fingerprint=fingerprint,
                consume=True,
            ):
                return

        args_preview = json.dumps(
            operation_call.arguments or {},
            ensure_ascii=False,
            default=str,
        )[:600]
        raise ConfirmationRequiredError(
            payload={
                "operation_fingerprint": fingerprint,
                "tool_slug": operation.operation_slug,
                "operation": operation.operation,
                "risk_level": operation.risk_level,
                "args_preview": args_preview,
                "summary": operation.description or "Operation requires explicit confirmation",
            }
        )

    @staticmethod
    def _find_operation(
        operation_slug: str,
        arguments: Dict[str, Any],
        operations: List[ResolvedOperation],
    ) -> Tuple[Optional[ResolvedOperation], Optional[str]]:
        for operation in operations:
            if operation.operation_slug == operation_slug:
                return operation, None
        shorthand_matches = [
            operation
            for operation in operations
            if operation.operation == operation_slug
        ]
        if len(shorthand_matches) == 1:
            return shorthand_matches[0], None
        if len(shorthand_matches) > 1:
            collection_slug = ""
            if isinstance(arguments, dict):
                collection_slug = str(arguments.get("collection_slug") or "").strip()
            if collection_slug:
                scoped_matches = [
                    operation
                    for operation in shorthand_matches
                    if str(getattr(operation, "collection_slug", "") or "").strip() == collection_slug
                ]
                if len(scoped_matches) == 1:
                    return scoped_matches[0], None
            candidates = ", ".join(
                operation.operation_slug for operation in shorthand_matches[:10]
            )
            return None, (
                f"Tool '{operation_slug}' is ambiguous. "
                "Provide collection_slug for the intended collection. "
                f"Matching bindings: {candidates}"
            )
        candidates = ", ".join(
            operation.operation_slug for operation in operations[:10]
        )
        if candidates:
            return None, (
                f"Tool '{operation_slug}' is unavailable. "
                f"Use a published canonical tool name. Available bindings: {candidates}"
            )
        return None, None

    @staticmethod
    def _coerce_args(arguments: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        """Coerce argument types to match schema (e.g., string->int for integer fields)."""
        if not isinstance(arguments, dict) or not isinstance(schema, dict):
            return arguments

        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return arguments

        coerced = dict(arguments)
        for key, value in coerced.items():
            prop_schema = properties.get(key, {})
            if not isinstance(prop_schema, dict):
                continue

            expected_type = prop_schema.get("type")
            if expected_type == "integer" and isinstance(value, str):
                # Try to coerce string to int
                try:
                    coerced[key] = int(value)
                except (ValueError, TypeError):
                    pass
            elif expected_type == "integer" and isinstance(value, float):
                # Coerce float to int (truncate)
                coerced[key] = int(value)
            elif expected_type == "number" and isinstance(value, str):
                # Try to coerce string to float
                try:
                    coerced[key] = float(value)
                except (ValueError, TypeError):
                    pass
            elif expected_type == "boolean" and isinstance(value, str):
                # Coerce common boolean strings
                if value.lower() in ("true", "1", "yes", "on"):
                    coerced[key] = True
                elif value.lower() in ("false", "0", "no", "off"):
                    coerced[key] = False
        return coerced

    @staticmethod
    def _validate_args(
        operation: ResolvedOperation,
        arguments: Dict[str, Any],
    ) -> Optional[OperationValidationError]:
        schema = build_prompt_input_schema(operation)
        if not schema:
            return None

        # Coerce types before validation to handle LLM passing strings instead of integers
        coerced_args = OperationExecutionFacade._coerce_args(arguments, schema)

        if _JSONSCHEMA_AVAILABLE and _jsonschema is not None:
            return OperationExecutionFacade._validate_args_jsonschema(coerced_args, schema)
        return OperationExecutionFacade._validate_args_builtin(coerced_args, schema)

    @staticmethod
    def _normalize_args(
        operation: ResolvedOperation,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        arguments = OperationExecutionFacade._normalize_template_fill_args(
            operation,
            arguments,
        )
        schema = build_prompt_input_schema(operation)
        if not schema or not isinstance(arguments, dict):
            return arguments
        stripped = OperationExecutionFacade._strip_optional_nulls(arguments, schema)
        return OperationExecutionFacade._apply_schema_defaults(stripped, schema)

    @staticmethod
    def _apply_schema_defaults(value: Any, schema: Dict[str, Any]) -> Any:
        """Expand JSON Schema defaults so equivalent effective calls share a key."""
        if not isinstance(schema, dict):
            return value
        if isinstance(value, dict):
            normalized = dict(value)
            properties = schema.get("properties")
            if not isinstance(properties, dict):
                return normalized
            for name, property_schema in properties.items():
                if name not in normalized and isinstance(property_schema, dict) and "default" in property_schema:
                    normalized[name] = copy.deepcopy(property_schema["default"])
                if name in normalized:
                    normalized[name] = OperationExecutionFacade._apply_schema_defaults(
                        normalized[name], property_schema if isinstance(property_schema, dict) else {})
            return normalized
        if isinstance(value, list) and isinstance(schema.get("items"), dict):
            return [OperationExecutionFacade._apply_schema_defaults(item, schema["items"]) for item in value]
        return value

    @staticmethod
    def _normalize_template_fill_args(
        operation: ResolvedOperation,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Preserve the template-fill envelope when an LLM flattens its values.

        ``collection.template.fill`` has operation arguments (``row_id`` and
        optional ``filename``) and a template-specific ``values`` object.  The
        latter can be deeply nested and native tool calling models sometimes
        put its keys at the operation root.  Restore the canonical envelope
        before schema validation; collection binding remains the executor's
        responsibility.
        """
        if (
            operation.operation != "collection.template.fill"
            or not isinstance(arguments, dict)
        ):
            return arguments

        normalized = dict(arguments)
        values = normalized.get("values")
        if isinstance(values, str):
            try:
                parsed_values = json.loads(values)
            except json.JSONDecodeError:
                # Some native tool adapters stringify Python dicts instead of
                # emitting JSON (single quotes, True/False/None).  Accept
                # only a literal container here; never execute the string.
                try:
                    parsed_values = ast.literal_eval(values)
                except (ValueError, SyntaxError):
                    parsed_values = None
            if isinstance(parsed_values, dict):
                normalized["values"] = parsed_values
            return normalized

        if "values" in normalized:
            return normalized

        reserved_keys = {"row_id", "filename", "collection_id", "collection_slug"}
        flattened_values = {
            key: value
            for key, value in normalized.items()
            if key not in reserved_keys
        }
        if not flattened_values:
            return normalized

        for key in flattened_values:
            normalized.pop(key, None)
        normalized["values"] = flattened_values
        return normalized

    @staticmethod
    def _strip_optional_nulls(
        arguments: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not isinstance(arguments, dict):
            return arguments
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return arguments
        required = {
            str(item).strip()
            for item in (schema.get("required") or [])
            if str(item).strip()
        }
        normalized = dict(arguments)
        changed = False
        for key, value in list(normalized.items()):
            child_schema = properties.get(key)
            if value is None and key not in required and not OperationExecutionFacade._schema_accepts_null(child_schema):
                normalized.pop(key, None)
                changed = True
                continue
            if isinstance(value, dict) and isinstance(child_schema, dict):
                nested = OperationExecutionFacade._strip_optional_nulls(value, child_schema)
                if nested is not value:
                    normalized[key] = nested
                    changed = True
        return normalized if changed else arguments


    @staticmethod
    def _schema_accepts_null(schema: Any) -> bool:
        if not isinstance(schema, dict):
            return False
        declared_type = schema.get("type")
        if declared_type == "null" or isinstance(declared_type, list) and "null" in declared_type:
            return True
        if schema.get("nullable") is True:
            return True
        return any(
            OperationExecutionFacade._schema_accepts_null(branch)
            for keyword in ("anyOf", "oneOf")
            for branch in schema.get(keyword, [])
        )

    @staticmethod
    def _validate_args_jsonschema(
        arguments: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> Optional[OperationValidationError]:
        validator = _jsonschema.Draft202012Validator(schema)
        errors = list(validator.iter_errors(arguments))
        if not errors:
            return None
        # Keep the runtime error contract deterministic across validator
        # versions.  Unknown fields are envelope errors and take precedence
        # over errors inside otherwise known fields, matching the built-in
        # validator used by minimal deployments.
        error = min(
            enumerate(errors),
            key=lambda item: (0 if item[1].validator == "additionalProperties" else 1, item[0]),
        )[1]
        field_path = "$"
        for part in error.absolute_path:
            if isinstance(part, str) and part.isidentifier():
                field_path += f".{part}"
            elif isinstance(part, str):
                field_path += f"[{part!r}]"
            else:
                field_path += f"[{part}]"
        return OperationValidationError(
            code=RuntimeErrorCode.OPERATION_INVALID_ARGS,
            message=error.message,
            field_path=field_path,
            retryable=True,
        )

    @staticmethod
    def _validate_args_builtin(
        arguments: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> Optional[OperationValidationError]:
        def _type_ok(value: Any, expected: str) -> bool:
            if expected == "object":
                return isinstance(value, dict)
            if expected == "array":
                return isinstance(value, list)
            if expected == "string":
                return isinstance(value, str)
            if expected == "integer":
                return isinstance(value, int) and not isinstance(value, bool)
            if expected == "number":
                return isinstance(value, (int, float)) and not isinstance(value, bool)
            if expected == "boolean":
                return isinstance(value, bool)
            if expected == "null":
                return value is None
            return True

        def _validate(value: Any, node: Dict[str, Any], path: str) -> Optional[OperationValidationError]:
            expected_type = node.get("type")
            if isinstance(expected_type, str) and not _type_ok(value, expected_type):
                return OperationValidationError(
                    code=RuntimeErrorCode.OPERATION_INVALID_ARGS,
                    message=f"{path} must be {expected_type}",
                    field_path=path,
                    retryable=True,
                )

            if "enum" in node and isinstance(node["enum"], list) and value not in node["enum"]:
                return OperationValidationError(
                    code=RuntimeErrorCode.OPERATION_INVALID_ARGS,
                    message=f"{path} must be one of: {', '.join(map(str, node['enum']))}",
                    field_path=path,
                    retryable=True,
                )

            if isinstance(value, (int, float)) and not isinstance(value, bool):
                minimum = node.get("minimum")
                if minimum is not None and value < minimum:
                    return OperationValidationError(
                        code=RuntimeErrorCode.OPERATION_INVALID_ARGS,
                        message=f"{path} must be >= {minimum}",
                        field_path=path,
                        retryable=True,
                    )

            if isinstance(value, dict):
                required = node.get("required", [])
                if isinstance(required, list):
                    for field in required:
                        if field not in value:
                            return OperationValidationError(
                                code=RuntimeErrorCode.OPERATION_INVALID_ARGS,
                                message=f"Missing required field: {field}",
                                field_path=f"{path}.{field}" if path != "$" else f"$.{field}",
                                retryable=True,
                            )
                properties = node.get("properties", {})
                additional_allowed = node.get("additionalProperties", True)
                if additional_allowed is False and isinstance(properties, dict):
                    for key in value:
                        if key not in properties:
                            return OperationValidationError(
                                code=RuntimeErrorCode.OPERATION_INVALID_ARGS,
                                message=f"Unexpected field(s): {key}",
                                field_path=path,
                                retryable=True,
                            )
                if isinstance(properties, dict):
                    for key, child_schema in properties.items():
                        if key in value and isinstance(child_schema, dict):
                            child_path = f"{path}.{key}" if path != "$" else f"$.{key}"
                            err = _validate(value[key], child_schema, child_path)
                            if err:
                                return err

            if isinstance(value, list):
                items_schema = node.get("items")
                if isinstance(items_schema, dict):
                    for idx, item in enumerate(value):
                        child_path = f"{path}[{idx}]"
                        err = _validate(item, items_schema, child_path)
                        if err:
                            return err
            return None

        return _validate(arguments, schema, "$")

    @staticmethod
    def format_result_for_context(
        result: ToolResult,
        *,
        operation_slug: Optional[str] = None,
        evidence_call_id: Optional[str] = None,
        stored_result: Optional[Dict[str, Any]] = None,
        context_budget_tokens: Optional[int] = None,
        context_model: Optional[str] = None,
    ) -> str:
        """Format a bounded, action-oriented tool result for the next LLM turn.

        Dataset operation payloads live in the dedicated result store. Inline
        output is preserved only when complete; otherwise the model gets a
        pointer and must call result.analyze instead of receiving a clipped,
        misleading prefix. Explicit direct results preserve their complete
        domain payload and bypass dataset presentation limits.
        """
        from app.services.tool_result_store import _json_dumps_exact

        def _fits_result_budget(rendered: str) -> bool:
            budget = context_budget_tokens
            if budget is None:
                from app.core.config import get_settings
                budget = get_settings().TOOL_RESULTS_CONTEXT_TOKENS
            from app.adapters.impl.llm_context import estimate_request_tokens
            return estimate_request_tokens({"model": context_model, "messages": [
                {"role": "tool", "content": rendered},
            ]}) <= budget

        def fits_budget(rendered: str) -> bool:
            if context_budget_tokens is None:
                return True
            from app.adapters.impl.llm_context import estimate_request_tokens
            return estimate_request_tokens({"model": context_model, "messages": [
                {"role": "tool", "content": rendered},
            ]}) <= context_budget_tokens

        def limited_result() -> str:
            if stored_result:
                limitation = ModelResultView(
                    result_id=str(stored_result.get("result_id") or ""),
                    revision=int(stored_result.get("revision") or 1),
                    source_coverage=SourceCoverage(complete=stored_result.get("source_complete"),
                        total=stored_result.get("source_total"), stored_count=stored_result.get("row_count", 0)),
                    delivery="direct" if result.delivery == "direct" and result.metadata.get("direct_recovery") else None,
                    recovery_reason=(str(result.metadata.get("direct_recovery", {}).get("reason"))
                                     if isinstance(result.metadata.get("direct_recovery"), dict) else None),
                    next_action=ResultNextAction(arguments={"result_id": str(stored_result.get("result_id") or ""),
                        "revision": int(stored_result.get("revision") or 1), "offset": 0, "limit": 5},
                        message="Read a smaller page with result.read."),
                ).model_dump(exclude_none=True)
            else:
                limitation = ResultUnavailable(reason="context_budget_exceeded",
                    message="The complete response exceeds the available context; retry with a narrower request.").model_dump()
            return _json_dumps_exact(limitation, ensure_ascii=False)

        if result.success:
            if result.delivery == "direct":
                # Domain tools bound their own payloads. Preserve complete JSON
                # rather than applying dataset/pointer or character truncation.
                output = dict(result.data) if isinstance(result.data, dict) else {"value": result.data}
                if evidence_call_id:
                    output["evidence_call_id"] = evidence_call_id
                rendered = _json_dumps_exact(output, ensure_ascii=False, default=str)
                return rendered if fits_budget(rendered) else limited_result()
            if result.metadata.get("workspace_view") and not stored_result:
                output = dict(result.data) if isinstance(result.data, dict) else {"value": result.data}
                if operation_slug == "result.read":
                    result_id = str(output.get("result_id") or "")
                    revision = int(output.get("revision") or 1)
                    values = output.get("value")
                    preserve_records = "value" in output and not output.get("record_too_large")
                    nested_text_more = output.get("next_text_offset") is not None
                    nested_children_more = output.get("next_child_offset") is not None
                    row_more = output.get("next_offset") is not None
                    nested_more = nested_text_more or nested_children_more
                    next_read_args: Dict[str, Any] | None = None
                    if nested_more or row_more:
                        next_read_args = {
                            "result_id": result_id,
                            "revision": revision,
                            "offset": output.get("offset", 0) if nested_more else output.get("next_offset"),
                            "limit": 1 if output.get("path") is not None else 10,
                            "view": output.get("view") or "auto",
                        }
                        if output.get("requested_fields") is not None:
                            next_read_args["fields"] = output["requested_fields"]
                        if output.get("path") is not None:
                            next_read_args["path"] = output["path"]
                            if output.get("text_limit") is not None:
                                next_read_args["text_offset"] = output.get("next_text_offset", 0) if nested_text_more else 0
                                next_read_args["text_limit"] = output.get("applied_text_limit") or output["text_limit"]
                            if output.get("child_limit") is not None:
                                next_read_args["child_offset"] = output.get("next_child_offset", 0) if nested_children_more else 0
                                next_read_args["child_limit"] = (len(values[0].get("children", []))
                                    if nested_children_more and values and isinstance(values[0], dict)
                                    else output["child_limit"])
                    view = ModelResultView(
                        result_id=result_id, revision=revision,
                        source_coverage=SourceCoverage(complete=output.get("source_complete"),
                                         total=output.get("source_total"), stored_count=output.get("loaded_items", 0)),
                        records=values if not output.get("record_too_large") else None,
                        offset=output.get("offset"), limit=output.get("limit"),
                        fields=output.get("requested_fields"), read_complete=output.get("read_complete"),
                        next_offset=output.get("next_offset"), path=output.get("path"),
                        text_offset=output.get("text_offset"), text_limit=output.get("text_limit"),
                        next_text_offset=output.get("next_text_offset"),
                        child_offset=output.get("child_offset"), child_limit=output.get("child_limit"),
                        next_child_offset=output.get("next_child_offset"),
                        view=output.get("view"),
                        snapshot_only=output.get("snapshot_only"),
                        imported_from=output.get("imported_from"),
                        next_action=(ResultNextAction(arguments={"result_id": result_id,
                            "revision": revision, "offset": 0, "limit": 1,
                            **({"path": output["path"], "text_limit": output.get("text_limit", 4000)}
                               if output.get("path") is not None else {})},
                            message="Inspect available fields, then read a smaller projection.") if output.get("record_too_large") else
                            ResultNextAction(arguments=next_read_args,
                            message="Continue reading the saved dataset.") if next_read_args is not None else None),
                    )
                    if output.get("record_too_large"):
                        view.next_action = ResultNextAction(tool="result.describe", arguments={"result_id": result_id},
                            message="Inspect available fields, then read a smaller projection.")
                    view_data = view.model_dump(exclude_none=True)
                    if preserve_records:
                        view_data["records"] = view.records
                    rendered = _json_dumps_exact(view_data, ensure_ascii=False, default=str)
                    if _fits_result_budget(rendered):
                        return rendered
                    view.records = None
                    view.next_action = ResultNextAction(tool="result.describe", arguments={"result_id": result_id},
                        message="Inspect available fields, then read a smaller projection.")
                    rendered = _json_dumps_exact(view.model_dump(exclude_none=True), ensure_ascii=False, default=str)
                    return rendered if _fits_result_budget(rendered) else limited_result()
                from app.core.config import get_settings
                budget = max(256, (context_budget_tokens or get_settings().TOOL_RESULTS_CONTEXT_TOKENS) * 3)
                def workspace_fits(value: Dict[str, Any]) -> bool:
                    rendered_value = _json_dumps_exact(value, ensure_ascii=False, default=str)
                    if context_budget_tokens is not None:
                        return fits_budget(rendered_value)
                    return len(rendered_value.encode()) <= budget

                if operation_slug == "result.history" and isinstance(output.get("items"), list):
                    items = list(output["items"])
                    original_count = len(items)
                    while items and not workspace_fits({**output, "items": items}):
                        items.pop()
                    output["items"] = items
                    output["returned_count"] = len(items)
                    output["truncated"] = len(items) < original_count or output.get("next_offset") is not None
                    if items and output["truncated"]:
                        next_offset = int(output.get("offset", 0)) + len(items)
                        output["next_offset"] = next_offset
                        output["catalog_complete"] = False
                        output["next_action"] = {"tool": "result.history", "arguments": {
                            "source_run_id": output.get("source_run_id"), "offset": next_offset,
                            "limit": min(int(output.get("limit", 30)), 50)},
                            "message": "Continue the metadata-only snapshot catalog."}
                    rendered_history = _json_dumps_exact(output, ensure_ascii=False, default=str)
                    if _fits_result_budget(rendered_history):
                        return rendered_history

                schema = output.get("observed_schema")
                if isinstance(schema, dict):
                    output["observed_schema"] = dict(list(schema.items())[:30])
                    output["schema_complete"] = output.get("schema_complete", True) and len(schema) <= 30
                while not workspace_fits(output) and output.get("observed_schema"):
                    output["observed_schema"].pop(next(reversed(output["observed_schema"])))
                    output["schema_complete"] = False
                while not workspace_fits(output) and output.get("sql_columns"):
                    output["sql_columns"].pop(next(reversed(output["sql_columns"])))
                    output["schema_returned_columns"] = len(output["sql_columns"])
                    output["schema_page_complete"] = False
                    output["next_schema_offset"] = (output.get("schema_offset", 0) + len(output["sql_columns"])) if output["sql_columns"] else None
                    output["schema_entry_too_large"] = not bool(output["sql_columns"])
                if not workspace_fits(output):
                    output.pop("sample", None)
                    output["sample_complete"] = False
                while not workspace_fits(output):
                    removable = next((key for key in ("schema_hint", "schema_query", "observed_schema", "fields")
                                      if key in output and output[key]), None)
                    if removable is None:
                        break
                    output.pop(removable, None)
                    output["schema_complete"] = False
                rendered = _json_dumps_exact(output, ensure_ascii=False, default=str)
                return rendered if workspace_fits(output) else limited_result()
            if stored_result:
                records = None
                payload = result.data
                if operation_slug == "result.import":
                    records = None
                elif not result.metadata.get("reused") and isinstance(payload, dict):
                    if payload.get("query_result_stored") is True and isinstance(payload.get("rows"), list):
                        records = payload["rows"]
                    elif isinstance(payload.get("value"), list) and isinstance(payload.get("meta"), dict):
                        records = payload["value"]
                    elif stored_result.get("row_count") == 1:
                        records = [payload]
                elif not result.metadata.get("reused") and isinstance(payload, list):
                    records = payload
                elif not result.metadata.get("reused") and stored_result.get("row_count") == 1:
                    records = [payload]
                if isinstance(records, list) and len(records) != stored_result.get("row_count"):
                    records = None
                view = ModelResultView(
                    status=("already_completed" if result.metadata.get("reused")
                            or (isinstance(payload, dict) and payload.get("status") == "already_imported") else "ready"),
                    result_id=str(stored_result.get("result_id") or ""),
                    revision=int(stored_result.get("revision") or 1),
                    source_coverage=SourceCoverage(complete=stored_result.get("source_complete"),
                        total=stored_result.get("source_total"), stored_count=stored_result.get("row_count", 0)),
                    snapshot_only=stored_result.get("snapshot_only"),
                    imported_from=stored_result.get("imported_from"),
                    records=records if isinstance(records, list) else None,
                    input_result_id=payload.get("input_result_id") if isinstance(payload, dict) else None,
                    input_revision=payload.get("input_revision") if isinstance(payload, dict) else None,
                    offset=payload.get("offset") if isinstance(payload, dict) else None,
                    limit=payload.get("limit") if isinstance(payload, dict) else None,
                    page_may_have_more=payload.get("page_may_have_more") if isinstance(payload, dict) else None,
                    query_complete=payload.get("query_complete") if isinstance(payload, dict) else None,
                    next_action=None if isinstance(records, list) else ResultNextAction(
                        arguments={"result_id": str(stored_result.get("result_id") or ""),
                                   "revision": int(stored_result.get("revision") or 1),
                                   "offset": 0, "limit": 10},
                        message="Read saved records with result.read.",
                    ),
                )
                if operation_slug == "result.import" and isinstance(payload, dict):
                    action = payload.get("next_action")
                    if isinstance(action, dict) and isinstance(action.get("arguments"), dict):
                        view.next_action = ResultNextAction(
                            tool="result.read", arguments=action["arguments"],
                            message=str(action.get("message") or "Read this imported historical snapshot."),
                        )
                if isinstance(payload, dict) and payload.get("operation") in {"aggregate", "find"}:
                    more = payload.get("page_may_have_more")
                    view.next_action = (ResultNextAction(
                        tool=f"result.{payload['operation']}",
                        arguments={**({"result_id": payload.get("input_result_id")} if payload.get("input_result_id") else {}),
                                   **({"revision": payload.get("input_revision")} if payload.get("input_revision") is not None else {}),
                                   "offset": int(payload.get("offset", 0)) + int(payload.get("limit", 0)),
                                   **({key: payload[key] for key in ("limit", "columns", "q") if key in payload})},
                        message="Continue the same query at the next offset; restart if input_revision is stale.",
                    ) if more else None)
                rendered = _json_dumps_exact(view.model_dump(exclude_none=True), ensure_ascii=False, default=str)
                if _fits_result_budget(rendered):
                    return rendered
                view.records = None
                view.next_action = ResultNextAction(tool="result.describe", arguments={
                    "result_id": view.result_id,
                }, message="Inspect available fields, then read a smaller projection.")
                rendered = _json_dumps_exact(view.model_dump(exclude_none=True), ensure_ascii=False, default=str)
                return rendered if _fits_result_budget(rendered) else limited_result()

            raw_output = result.data
            canonical_operation = OperationExecutionFacade._canonical_operation_name(operation_slug)
            if isinstance(raw_output, dict):
                # This ID is projected only into the follow-up LLM context as
                # bounded evidence metadata.
                raw_output = dict(raw_output)
                if canonical_operation == "collection.info":
                    raw_output = OperationExecutionFacade._compact_collection_info_for_context(
                        raw_output,
                    )
                elif canonical_operation == "collection.template.search":
                    raw_output = OperationExecutionFacade._compact_template_search_for_context(raw_output)
                elif canonical_operation == "collection.template.get_schema":
                    raw_output = OperationExecutionFacade._compact_template_schema_for_context(raw_output)
                elif canonical_operation == "collection.template.fill":
                    raw_output = OperationExecutionFacade._compact_template_fill_for_context(raw_output)
                # Compact projections return new dictionaries, so append the
                # runtime evidence reference only after projection.
                if evidence_call_id:
                    raw_output["evidence_call_id"] = evidence_call_id
            try:
                rendered = _json_dumps_exact(raw_output, ensure_ascii=False, default=str)
                if canonical_operation == "collection.info":
                    # Keep this diagnostic response parseable when a schema is large.
                    while not fits_budget(rendered):
                        sections = [
                            raw_output.get("field_profiles"),
                            raw_output.get("filter_hints"),
                            raw_output.get("fields"),
                            raw_output.get("remote_objects"),
                        ]
                        populated = [section for section in sections if isinstance(section, list) and section]
                        if not populated:
                            raw_output.pop("field_profiles", None)
                            raw_output.pop("filter_hints", None)
                            raw_output.pop("fields", None)
                            raw_output.pop("remote_objects", None)
                            collection = raw_output.get("collection") or {}
                            collection.pop("usage_rules", None)
                            rendered = _json_dumps_exact(raw_output, ensure_ascii=False, default=str)
                            break
                        max(populated, key=len).pop()
                        rendered = _json_dumps_exact(raw_output, ensure_ascii=False, default=str)
                    return rendered if fits_budget(rendered) else limited_result()
                return rendered if fits_budget(rendered) else limited_result()
            except Exception:
                rendered = str(raw_output)
                return rendered if fits_budget(rendered) else limited_result()
        failure = result.metadata.get("mcp_failure")
        if isinstance(failure, dict):
            rendered = _json_dumps_exact({"success": False, "failure": failure}, ensure_ascii=False, default=str)
            if fits_budget(rendered):
                return rendered
            compact_failure = {
                key: failure.get(key)
                for key in ("version", "kind", "category", "code", "message", "request_id", "stage", "http_status", "rpc_code", "user_message")
                if failure.get(key) is not None
            }
            compact_failure["details_truncated_for_context"] = True
            rendered = _json_dumps_exact({"success": False, "failure": compact_failure}, ensure_ascii=False, default=str)
            if fits_budget(rendered):
                return rendered
            return _json_dumps_exact({"success": False, "failure": {
                "version": failure.get("version", 1),
                "kind": failure.get("kind", "unknown"),
                "category": failure.get("category", "unknown"),
                "code": str(failure.get("code") or "unknown")[:80],
                "message": str(failure.get("message") or "MCP source failed")[:100],
                "details_truncated_for_context": True,
            }}, ensure_ascii=False)
        return f"Error: {result.error or 'unknown'}"

    @staticmethod
    def _canonical_operation_name(operation_slug: Optional[str]) -> str:
        normalized = str(operation_slug or "").strip()
        if normalized.startswith("instance."):
            _, _, normalized = normalized.partition(".")
            _, _, normalized = normalized.partition(".")
        return normalized

    @staticmethod
    def _compact_collection_info_for_context(
        raw_output: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Show bounded schema diagnostics; operation contracts are already published."""

        def text(value: Any, limit: int = MAX_COLLECTION_INFO_TEXT_CHARS) -> str:
            normalized = str(value or "").strip()
            return normalized[:limit]

        collection = raw_output.get("collection") or {}
        readiness = raw_output.get("readiness") or {}
        schema = raw_output.get("schema") or {}
        hints = (raw_output.get("filter_hints") or {}).get("fields") or {}
        enrichment = (raw_output.get("runtime_enrichment") or {}).get("data") or {}

        projection = {
            "collection": {
                key: value
                for key, value in {
                    "slug": text(collection.get("slug")),
                    "name": text(collection.get("name")),
                    "type": text(collection.get("type")),
                    "description": text(collection.get("description")),
                    "usage_rules": text(
                        collection.get("usage_rules"),
                        MAX_COLLECTION_INFO_RULES_CHARS,
                    ),
                }.items()
                if value
            },
            "readiness": {"status": text(readiness.get("status")), "schema_freshness": text(readiness.get("schema_freshness"))},
            "fields": [
                {
                    "name": text(field.get("name"), 100),
                    "type": text(field.get("data_type"), 40),
                    "description": text(field.get("description"), 160),
                    "filterable": bool(field.get("filterable")),
                }
                for field in (schema.get("fields") or [])[:24]
                if isinstance(field, dict)
            ],
            "filter_hints": [
                {
                    "field": text(name, 100),
                    "coverage": text(hint.get("coverage"), 40),
                    "choices": list(hint.get("choices") or [])[:8],
                    "top_values": list(hint.get("top_values") or [])[:5],
                }
                for name, hint in list(hints.items())[:12]
                if isinstance(hint, dict)
            ],
            "field_profiles": [
                {"field": text(name, 100), "complete": bool(profile.get("complete")),
                 "values": list(profile.get("values") or profile.get("top_values") or [])[:5]}
                for name, profile in list((enrichment.get("field_profiles") or {}).items())[:12]
                if isinstance(profile, dict)
            ],
            "remote_objects": list(enrichment.get("tables") or enrichment.get("entities") or [])[:12],
        }
        return projection

    @staticmethod
    def _compact_template_search_for_context(raw_output: Dict[str, Any]) -> Dict[str, Any]:
        """Publish template identities, not their repeated row schemas."""
        hits: List[Dict[str, Any]] = []
        for item in (raw_output.get("hits") or [])[:MAX_TEMPLATE_SEARCH_HITS]:
            if not isinstance(item, dict):
                continue
            row_data = item.get("row_data") if isinstance(item.get("row_data"), dict) else {}
            row_id = str(item.get("row_id") or row_data.get("id") or "").strip()
            if not row_id:
                continue
            title = str(row_data.get("title") or item.get("title") or "").strip()
            fragment = str(item.get("primary_fragment") or "").strip()
            entry: Dict[str, Any] = {"row_id": row_id}
            if title:
                entry["title"] = title[:MAX_TEMPLATE_SEARCH_TITLE_CHARS]
            if isinstance(item.get("score"), (int, float)):
                entry["score"] = item["score"]
            if fragment:
                entry["match"] = fragment[:MAX_TEMPLATE_SEARCH_FRAGMENT_CHARS]
            hits.append(entry)
        return {
            "collection": raw_output.get("collection"),
            "hits": hits,
            "total": len(hits),
        }

    @staticmethod
    def _compact_template_schema_for_context(raw_output: Dict[str, Any]) -> Dict[str, Any]:
        """The fill input schema is the sole schema needed by the next call."""
        schema = raw_output.get("template_schema")
        return {"template_schema": schema if isinstance(schema, dict) else {}}

    @staticmethod
    def _compact_template_fill_for_context(raw_output: Dict[str, Any]) -> Dict[str, Any]:
        """Expose only the artifact reference and its delivery metadata."""
        allowed = ("artifact_id", "file_name", "content_type", "size_bytes", "format")
        return {
            key: raw_output[key]
            for key in allowed
            if raw_output.get(key) not in (None, "")
        }

    @staticmethod
    def format_observation_text(tool_outputs: List[Dict[str, Any]]) -> str:
        """Build observation text from all tool outputs for synthesis."""
        import json as _json
        from app.services.tool_result_store import _json_dumps_exact

        parts = []
        for out in tool_outputs:
            tool_name = out.get("operation") or out.get("tool") or "unknown"
            if out.get("success") and out.get("data"):
                data = out["data"]
                # Pretty-print downloadable file results as markdown links
                if tool_name in (
                    "file.generate",
                    "file_generate",
                    "collection.template.fill",
                    "instance.local-template-tools.collection.template.fill",
                ):
                    file_name = data.get("file_name") or data.get("filename") or "file"
                    artifact_id = data.get("artifact_id") or ""
                    size_bytes = data.get("size_bytes")
                    size_str = f" ({size_bytes} bytes)" if size_bytes else ""
                    data_str = f"📎 {file_name}{size_str} — artifact_id: `{artifact_id}`"
                else:
                    try:
                        data_str = _json_dumps_exact(
                            data, ensure_ascii=False, default=str,
                        )[:4000]
                    except Exception:
                        data_str = str(data)[:4000]
                parts.append(f"[{tool_name}] OK:\n{data_str}")
            elif out.get("error"):
                parts.append(f"[{tool_name}] ERROR: {out['error']}")

        return "\n\n".join(parts) or "No data retrieved."

    @staticmethod
    def make_summary(tool_name: str, result: ToolResult) -> str:
        """Build short summary from tool result for Observation."""
        if not result.success:
            return f"{tool_name} failed: {result.error or 'unknown'}"

        data = result.data or {}
        parts = [f"{tool_name} OK"]

        if "count" in data:
            parts.append(f"count={data['count']}")
        if "id" in data:
            parts.append(f"id={data['id']}")
        if "status" in data:
            parts.append(f"status={data['status']}")
        if "hits" in data and isinstance(data["hits"], list):
            parts.append(f"hits={len(data['hits'])}")
        if "message" in data:
            msg = str(data["message"])[:80]
            parts.append(f"msg={msg}")

        return ". ".join(parts)

ToolExecutor = OperationExecutionFacade
