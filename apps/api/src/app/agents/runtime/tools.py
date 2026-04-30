"""
OperationExecutor — выполнение operation calls с таймаутами, валидацией и логированием.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple

try:
    import jsonschema as _jsonschema
except ImportError:
    _jsonschema = None  # type: ignore[assignment]

_JSONSCHEMA_AVAILABLE = _jsonschema is not None

from app.agents.context import OperationCall, ToolContext, ToolResult
from app.agents.contracts import ResolvedOperation
from app.agents.runtime.confirmation import (
    ConfirmationService,
    build_operation_fingerprint,
    get_confirmation_service,
)
from app.agents.runtime.tool_reuse_policy import ToolCallReusePolicy
from app.core.logging import get_logger
from app.runtime.operation_errors import (
    OperationExecutionError,
    OperationValidationError,
    RuntimeErrorCode,
)

logger = get_logger(__name__)


class ConfirmationRequiredError(RuntimeError):
    def __init__(self, payload: Dict[str, Any]) -> None:
        super().__init__(str(payload.get("summary") or "Operation requires confirmation"))
        self.payload = payload


class OperationExecutionFacade:
    """Execute operation calls with validation, timeouts, and source extraction."""
    def __init__(
        self,
        confirmation_service: Optional[ConfirmationService] = None,
        reuse_policy: Optional[ToolCallReusePolicy] = None,
    ) -> None:
        self._confirmation_service = confirmation_service or get_confirmation_service()
        self._reuse_policy = reuse_policy or ToolCallReusePolicy()

    async def execute(
        self,
        operation_call: OperationCall,
        ctx: ToolContext,
        operations: List[ResolvedOperation],
        timeout_s: Optional[int] = None,
    ) -> Tuple[ToolResult, List[dict]]:
        """Execute a single operation call.

        Returns:
            Tuple of (ToolResult, sources list for RAG-like tools)

        Tool logs (from ToolLogger) are automatically extracted from
        result.metadata["logs"] and available for RunStore persistence.
        """
        operation, resolved_slug_error = self._find_operation(
            operation_call.operation_slug,
            operations,
        )

        if not operation:
            logger.error(f"Operation not found: {operation_call.operation_slug}")
            message = resolved_slug_error or f"Operation '{operation_call.operation_slug}' not found"
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

        if operation.operation_slug != operation_call.operation_slug:
            logger.info(
                "Resolved shorthand operation '%s' -> '%s'",
                operation_call.operation_slug,
                operation.operation_slug,
            )
            operation_call = OperationCall(
                id=operation_call.id,
                operation_slug=operation.operation_slug,
                arguments=operation_call.arguments,
            )

        validation_error = self._validate_args(operation, operation_call.arguments)
        if validation_error:
            logger.warning(
                "Operation args validation failed: %s (%s)",
                validation_error.message,
                validation_error.field_path or "root",
            )
            return ToolResult.fail(
                validation_error.to_user_message(),
                **validation_error.to_metadata(),
            ), []

        self._ensure_confirmation_if_required(
            operation=operation,
            operation_call=operation_call,
            ctx=ctx,
        )

        reused = self._reuse_policy.maybe_reuse(
            operation_slug=operation_call.operation_slug,
            arguments=operation_call.arguments,
            ctx=ctx,
        )
        if reused is not None:
            result, sources = reused
            logger.info(
                "Reused tool result for operation '%s' from in-turn ledger",
                operation_call.operation_slug,
            )
            return result, sources

        try:
            logger.info(f"Executing operation: {operation_call.operation_slug}")
            executor = ctx.get_runtime_deps().operation_executor
            if not executor:
                err = OperationExecutionError(
                    code=RuntimeErrorCode.OPERATION_EXECUTION_FAILED,
                    message="Operation executor is not configured",
                    retryable=False,
                )
                return ToolResult.fail(err.message, **err.to_metadata()), []

            if timeout_s is not None:
                result = await asyncio.wait_for(
                    executor.execute(operation_call, ctx), timeout=timeout_s,
                )
            else:
                result = await executor.execute(operation_call, ctx)

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
                        f"Operation '{operation_call.operation_slug}' produced "
                        f"{warning_count} warnings/errors",
                    )

            return result, sources

        except asyncio.TimeoutError:
            logger.error(
                f"Operation {operation_call.operation_slug} timed out after {timeout_s}s",
            )
            err = OperationExecutionError(
                code=RuntimeErrorCode.OPERATION_TIMEOUT,
                message=f"Execution timed out after {timeout_s} seconds",
                retryable=True,
            )
            return ToolResult.fail(err.message, **err.to_metadata()), []

        except Exception as e:
            logger.error(
                f"Operation {operation_call.operation_slug} execution failed: {e}",
                exc_info=True,
            )
            err = OperationExecutionError(
                code=RuntimeErrorCode.OPERATION_EXECUTION_FAILED,
                message=str(e),
                retryable=True,
            )
            return ToolResult.fail(err.message, **err.to_metadata()), []

    def _ensure_confirmation_if_required(
        self,
        *,
        operation: ResolvedOperation,
        operation_call: OperationCall,
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
            # Sandbox/non-chat execution must provide an explicit pre-approval
            # list from the caller; otherwise confirmation is required.
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
        operations: List[ResolvedOperation],
    ) -> Tuple[Optional[ResolvedOperation], Optional[str]]:
        for operation in operations:
            if operation.operation_slug == operation_slug:
                return operation, None

        short_matches = [
            operation
            for operation in operations
            if operation.operation == operation_slug
        ]
        if len(short_matches) == 1:
            return short_matches[0], None
        if len(short_matches) > 1:
            candidates = ", ".join(
                operation.operation_slug for operation in short_matches[:10]
            )
            return None, (
                f"Operation '{operation_slug}' is ambiguous. "
                f"Use one of: {candidates}"
            )

        # Fallback: try underscore→dot normalization (e.g. netbox_get_objects → netbox.get_objects)
        if "_" in operation_slug and "." not in operation_slug:
            normalized = operation_slug.replace("_", ".", 1)
            dot_matches = [op for op in operations if op.operation == normalized]
            if len(dot_matches) == 1:
                return dot_matches[0], None
            if len(dot_matches) > 1:
                candidates = ", ".join(op.operation_slug for op in dot_matches[:10])
                return None, (
                    f"Operation '{operation_slug}' is ambiguous. "
                    f"Use one of: {candidates}"
                )

        return None, None

    @staticmethod
    def _validate_args(
        operation: ResolvedOperation,
        arguments: Dict[str, Any],
    ) -> Optional[OperationValidationError]:
        schema = operation.input_schema or {}
        if not schema:
            return None
        if _jsonschema is not None:
            return OperationExecutionFacade._validate_args_jsonschema(arguments, schema)
        return OperationExecutionFacade._validate_args_builtin(arguments, schema)

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
    def format_result_for_context(result: ToolResult) -> str:
        """Format tool result as text for LLM context."""
        import json as _json

        if result.success:
            raw_output = result.data or {}
            try:
                return _json.dumps(raw_output, ensure_ascii=False, default=str)[:4000]
            except Exception:
                return str(raw_output)[:4000]
        return f"Error: {result.error or 'unknown'}"

    @staticmethod
    def format_observation_text(tool_outputs: List[Dict[str, Any]]) -> str:
        """Build observation text from all tool outputs for synthesis."""
        import json as _json

        parts = []
        for out in tool_outputs:
            tool_name = out.get("operation") or out.get("tool") or "unknown"
            if out.get("success") and out.get("data"):
                try:
                    data_str = _json.dumps(
                        out["data"], ensure_ascii=False, default=str,
                    )[:4000]
                except Exception:
                    data_str = str(out["data"])[:4000]
                parts.append(f"[{tool_name}] OK:\n{data_str}")
            elif out.get("error"):
                parts.append(f"[{tool_name}] ERROR: {out['error']}")

        return "\n\n".join(parts) or "No data retrieved."

    @staticmethod
    def make_summary(operation_slug: str, result: ToolResult) -> str:
        """Build short summary from operation result for Observation."""
        if not result.success:
            return f"{operation_slug} failed: {result.error or 'unknown'}"

        data = result.data or {}
        parts = [f"{operation_slug} OK"]

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


# Backward-compatible aliases.
OperationExecutor = OperationExecutionFacade
ToolExecutor = OperationExecutionFacade
