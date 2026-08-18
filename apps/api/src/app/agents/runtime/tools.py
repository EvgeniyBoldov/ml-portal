"""Runtime tool execution with validation, timeouts, and confirmation gates."""
from __future__ import annotations

import asyncio
import ast
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
from app.agents.runtime.tool_reuse_policy import ToolCallReusePolicy
from app.core.logging import get_logger
from app.runtime.error_payloads import build_debug_payload, build_error_metadata
from app.runtime.operation_errors import (
    OperationExecutionError,
    OperationValidationError,
    RuntimeErrorCode,
)

logger = get_logger(__name__)


# The full operation result remains in the canonical journal and observation
# output. These limits only govern the follow-up prompt used to choose the
# next operation.
MAX_TOOL_CONTEXT_CHARS = 4_000
MAX_COLLECTION_INFO_TOOLS = 12
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
        timeout_s: Optional[int] = None,
    ) -> Tuple[ToolResult, List[dict]]:
        """Execute a single operation call.

        Returns:
            Tuple of (ToolResult, sources list for RAG-like tools)

        Bounded tool diagnostics (from ToolExecutionNotes) are attached to
        result.metadata["logs"] and become part of the canonical tool result.
        """
        original_operation_slug = operation_call.tool_name
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

        collection_gate_error = self._validate_collection_interaction(
            operation=operation,
            ctx=ctx,
        )
        if collection_gate_error is not None:
            return ToolResult.fail(
                collection_gate_error.message,
                **{
                    **collection_gate_error.to_metadata(),
                    "user_message": collection_gate_error.message,
                    "operator_message": collection_gate_error.message,
                    "source": "runtime",
                },
            ), []

        if (
            original_operation_slug == "collection.info"
            and isinstance(operation_call.arguments, dict)
            and any(key in operation_call.arguments for key in ("collection_slug", "collection_id"))
        ):
            stripped_arguments = dict(operation_call.arguments)
            stripped_arguments.pop("collection_slug", None)
            stripped_arguments.pop("collection_id", None)
            operation_call = ToolCall(
                id=operation_call.id,
                tool_name=operation_call.tool_name,
                arguments=stripped_arguments,
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

        self._ensure_confirmation_if_required(
            operation=operation,
            operation_call=operation_call,
            ctx=ctx,
        )

        reused = self._reuse_policy.maybe_reuse(
            operation_slug=operation_call.tool_name,
            arguments=operation_call.arguments,
            ctx=ctx,
        )
        if reused is not None:
            result, sources = reused
            logger.info(
                "Reused tool result for tool '%s' from in-turn ledger",
                operation_call.tool_name,
            )
            return result, sources

        try:
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
            ctx.extra["runtime_active_tool_call_id"] = operation_call.id
            ctx.extra["runtime_active_tool_slug"] = operation_call.tool_name
            try:
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

            return result, sources

        except asyncio.TimeoutError:
            logger.error(
                f"Tool {operation_call.tool_name} timed out after {timeout_s}s",
            )
            err = OperationExecutionError(
                code=RuntimeErrorCode.OPERATION_TIMEOUT,
                message=f"Execution timed out after {timeout_s} seconds",
                retryable=True,
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
                        context={"tool": operation_call.tool_name, "timeout_seconds": timeout_s},
                    ),
                ),
            ), []

        except Exception as e:
            logger.error(
                f"Tool {operation_call.tool_name} execution failed: {e}",
                exc_info=True,
            )
            err = OperationExecutionError(
                code=RuntimeErrorCode.OPERATION_EXECUTION_FAILED,
                message=str(e),
                retryable=True,
            )
            return ToolResult.fail(
                err.message,
                **build_error_metadata(
                    error_code=err.code.value,
                    retryable=err.retryable,
                    user_message=err.message,
                    operator_message=str(e),
                    source="tool",
                    debug=build_debug_payload(
                        exc=e,
                        context={"tool": operation_call.tool_name},
                    ),
                ),
            ), []

    def _ensure_confirmation_if_required(
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
            if self._confirmation_service.verify(
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
            if operation_slug == "collection.info" and collection_slug:
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
                f"Use exact invoke name. Matching tools: {candidates}"
            )
        candidates = ", ".join(
            operation.operation_slug for operation in operations[:10]
        )
        if candidates:
            return None, (
                f"Tool '{operation_slug}' is unavailable. "
                f"Use exact invoke name from the prompt. Available examples: {candidates}"
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
        return OperationExecutionFacade._strip_optional_nulls(arguments, schema)

    @staticmethod
    def _validate_collection_interaction(
        *,
        operation: ResolvedOperation,
        ctx: ToolContext,
    ) -> Optional[OperationValidationError]:
        """Require a successful ``collection.info`` before collection use.

        AgentRuntime opts into this gate for every execution.  Keeping the
        state on ``ToolContext`` makes the check apply to both native and text
        tool calls, while preserving compatibility for non-agent callers.
        """
        state = ctx.extra.get("collection_interaction_state")
        if not isinstance(state, dict) or not state.get("enabled"):
            return None
        if operation.scope != "collection" or operation.operation == "collection.info":
            return None
        active_slugs = state.get("active_operation_slugs") or set()
        if operation.operation_slug in active_slugs:
            return None
        collection_slug = str(getattr(operation, "collection_slug", "") or "").strip()
        message = (
            f"Call collection.info for collection '{collection_slug}' before using this operation."
            if collection_slug
            else "Call collection.info before using this collection operation."
        )
        code = (
            RuntimeErrorCode.COLLECTION_OPERATION_NOT_ACTIVATED
            if state.get("opened_collections")
            else RuntimeErrorCode.COLLECTION_INFO_REQUIRED
        )
        return OperationValidationError(code=code, message=message, retryable=True)

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
            if value is None and key not in required:
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
    def _validate_args_jsonschema(
        arguments: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> Optional[OperationValidationError]:
        validator = _jsonschema.Draft202012Validator(schema)
        error = next(iter(validator.iter_errors(arguments)), None)
        if error is None:
            return None
        field_path = "$" + "".join(
            f"[{p!r}]" if isinstance(p, str) else f"[{p}]"
            for p in error.absolute_path
        ) if error.absolute_path else "$"
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
        include_operation_contracts: bool = True,
    ) -> str:
        """Format a bounded, action-oriented tool result for the next LLM turn.

        Each operation may publish a compact LLM projection which is distinct
        from its complete result. Full results remain in the canonical journal
        and ``AgentLoopState.tool_outputs``. This avoids asking the operation
        loop to infer which arbitrary fields are safe to discard while keeping
        the next tool decision supplied with its declared contract.
        """
        import json as _json

        if result.success:
            raw_output = result.data or {}
            canonical_operation = OperationExecutionFacade._canonical_operation_name(operation_slug)
            if isinstance(raw_output, dict):
                if canonical_operation == "collection.info":
                    raw_output = OperationExecutionFacade._compact_collection_info_for_context(
                        raw_output,
                        include_operation_contracts=include_operation_contracts,
                    )
                elif canonical_operation == "collection.template.search":
                    raw_output = OperationExecutionFacade._compact_template_search_for_context(raw_output)
                elif canonical_operation == "collection.template.get_schema":
                    raw_output = OperationExecutionFacade._compact_template_schema_for_context(raw_output)
                elif canonical_operation == "collection.template.fill":
                    raw_output = OperationExecutionFacade._compact_template_fill_for_context(raw_output)
            try:
                return _json.dumps(raw_output, ensure_ascii=False, default=str)[
                    :MAX_TOOL_CONTEXT_CHARS
                ]
            except Exception:
                return str(raw_output)[:MAX_TOOL_CONTEXT_CHARS]
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
        *,
        include_operation_contracts: bool,
    ) -> Dict[str, Any]:
        """Return the minimum collection.info contract required by an agent."""

        def text(value: Any, limit: int = MAX_COLLECTION_INFO_TEXT_CHARS) -> str:
            normalized = str(value or "").strip()
            return normalized[:limit]

        collection = raw_output.get("collection") or {}
        readiness = raw_output.get("readiness") or {}
        tools = raw_output.get("tools") or []

        compact_tools: List[Dict[str, Any]] = []
        if isinstance(tools, list):
            for item in tools[:MAX_COLLECTION_INFO_TOOLS]:
                if not isinstance(item, dict):
                    continue
                compact_tools.append(
                    {
                        key: value
                        for key, value in {
                            "tool_name": text(item.get("tool_name")),
                            "invoke_as": text(item.get("invoke_as")),
                            "description": text(item.get("description")),
                            "arguments": item.get("arguments")
                            if isinstance(item.get("arguments"), list)
                            else [],
                        }.items()
                        if value not in ("", [])
                    }
                )

        projection = {
            "collection": {
                key: value
                for key, value in {
                    "id": text(collection.get("id")),
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
            "readiness": {
                key: value
                for key, value in {
                    "status": text(readiness.get("status")),
                    "schema_freshness": text(readiness.get("schema_freshness")),
                    "operations_count": readiness.get("operations_count"),
                }.items()
                if value not in ("", None)
            },
        }
        # A native tools payload is the authoritative operation contract. The
        # list below is required only by the plaintext tool-call protocol.
        if include_operation_contracts:
            projection["tools"] = compact_tools
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
                        data_str = _json.dumps(
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
