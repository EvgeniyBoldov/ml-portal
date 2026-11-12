from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlsplit

import httpx

from app.agents.context import ToolCall, ToolContext, ToolResult
from app.agents.contracts import OperationCredentialContext, ProviderExecutionTarget
from app.agents.registry import ToolRegistry
from app.agents.runtime_graph import OperationExecutionBinding, RuntimeExecutionGraph
from app.core.config import (
    get_settings,
    mcp_credential_broker_enabled,
    mcp_credential_broker_required,
    mcp_raw_credential_fallback_allowed,
)
from app.core.http.tls import outbound_http_verify
from app.services.mcp_credential_broker_service import MCPCredentialBrokerService
from app.services.mcp_jsonrpc_client import parse_mcp_response as _parse_mcp_response_body
from portal_mcp_contract import MCPFailure, MCPFailureCategory, MCPFailureKind, is_sensitive_key, normalize_failure, public_user_message, safe_diagnostic
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType


logger = logging.getLogger(__name__)


def _safe_url_origin(value: str) -> str:
    try:
        parsed = urlsplit(str(value or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "unknown"
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        return f"{parsed.scheme}://{host}{':' + str(parsed.port) if parsed.port else ''}"
    except (TypeError, ValueError):
        return "unknown"


def _safe_transport_cause(exc: BaseException) -> tuple[str, str, str]:
    cause = exc.__cause__ or exc.__context__
    if cause is None:
        return "-", "-", "-"
    reason = str(getattr(cause, "strerror", "") or "-").replace("\n", " ").replace("\r", " ")[:120]
    return type(cause).__name__, str(getattr(cause, "errno", "-") or "-"), reason


def _mcp_call_secrets(arguments: Dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []

    def collect(value: Any, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                lowered = str(child_key).lower()
                if isinstance(child, str) and is_sensitive_key(lowered):
                    values.append(child)
                else:
                    collect(child, lowered)
        elif isinstance(value, list):
            for child in value:
                collect(child, key)

    collect(arguments)
    return tuple(item for item in values if item)


def _mcp_user_message(category: MCPFailureCategory) -> str:
    return public_user_message(category)


@dataclass(slots=True)
class _UnifiedToolCall:
    """Normalized runtime tool call (local and remote share this shape)."""

    name: str
    arguments: Dict[str, Any]
    target: ProviderExecutionTarget


class MissingOperationCredentialsError(ValueError):
    """Safe, actionable failure raised before sending an unauthenticated MCP call."""

    def __init__(
        self,
        *,
        operation: str,
        data_instance_slug: str,
        credential_policy: str,
    ) -> None:
        self.operation = operation
        self.data_instance_slug = data_instance_slug
        self.credential_policy = credential_policy
        required_scope = (
            "a user-owned credential"
            if credential_policy == "user_only"
            else "a credential owned by the user, tenant, or platform"
        )
        super().__init__(
            f"Credentials are unavailable for operation '{operation}' on data instance "
            f"'{data_instance_slug}'; this operation requires {required_scope}. "
            "No upstream request was sent."
        )


class MCPFailureError(ValueError):
    def __init__(self, failure: Dict[str, Any]) -> None:
        self.mcp_failure = failure
        super().__init__(str(failure.get("user_message") or "The MCP source request failed."))


class DirectOperationExecutor:
    # OperationExecutionFacade requires this trusted handshake before allowing
    # durable non-cacheable calls from a persisted task.
    supports_runtime_execution_guard = True

    def __init__(self, *, tool_registry: Optional["ToolRegistry"] = None) -> None:
        self._tool_registry = tool_registry or ToolRegistry.get_instance()
        self._clients: Dict[str, httpx.AsyncClient] = {}
        self._mcp_sessions: Dict[str, tuple[str, float]] = {}
        self._client_lock = asyncio.Lock()
        self._mcp_session_lock = asyncio.Lock()
        settings = get_settings()
        self._http_max_retries = max(0, int(getattr(settings, "HTTP_MAX_RETRIES", 0) or 0))
        self._retry_base_delay_ms = 200
        self._mcp_session_ttl_s: int = max(30, int(getattr(settings, "MCP_SESSION_TTL_S", 300) or 300))
        self._mcp_credential_broker_enabled = mcp_credential_broker_enabled(settings)
        self._mcp_credential_broker_required = mcp_credential_broker_required(settings)
        self._mcp_allow_raw_credential_fallback = mcp_raw_credential_fallback_allowed(settings)
        logger.info(
            "runtime_mcp_credential_delivery_policy environment=%s configured_broker_enabled=%s "
            "configured_broker_required=%s configured_raw_fallback=%s effective_broker_enabled=%s "
            "effective_broker_required=%s effective_raw_fallback=%s broker_base_url_present=%s "
            "broker_resolve_path_present=%s",
            settings.ENV,
            settings.MCP_CREDENTIAL_BROKER_ENABLED,
            settings.MCP_CREDENTIAL_BROKER_REQUIRED,
            settings.MCP_ALLOW_RAW_CREDENTIAL_FALLBACK,
            self._mcp_credential_broker_enabled,
            self._mcp_credential_broker_required,
            self._mcp_allow_raw_credential_fallback,
            bool(settings.MCP_CREDENTIAL_BROKER_BASE_URL),
            bool(settings.MCP_CREDENTIAL_BROKER_RESOLVE_PATH),
        )

    async def aclose(self) -> None:
        clients, self._clients = list(self._clients.values()), {}
        self._mcp_sessions.clear()
        await asyncio.gather(*(client.aclose() for client in clients), return_exceptions=True)

    async def execute(self, operation_call: ToolCall, ctx: ToolContext) -> ToolResult:
        call_id = str(ctx.extra.get("runtime_active_tool_call_id") or operation_call.id or "-")
        run_id = str(ctx.extra.get("run_id") or ctx.extra.get("runtime_run_id") or "-")
        logger.info(
            "runtime_tool_dispatch_started run_id=%s call_id=%s operation=%s",
            run_id,
            call_id,
            operation_call.tool_name,
        )
        binding, target = self._resolve_target_binding(operation_call.tool_name, ctx)
        if not target:
            logger.warning(
                "runtime_tool_dispatch_failed run_id=%s call_id=%s operation=%s stage=target_resolution error_type=TargetNotFound",
                run_id,
                call_id,
                operation_call.tool_name,
            )
            return ToolResult.fail(f"Execution target not found for '{operation_call.tool_name}'")

        if target.provider_type == "local":
            handler_slug = target.handler_slug
            if not handler_slug:
                return ToolResult.fail(
                    f"Local handler missing for '{operation_call.tool_name}'"
                )
            try:
                merged_args = self._merge_local_args(target, operation_call.arguments, ctx, binding=binding)
            except ValueError as exc:
                return ToolResult.fail(str(exc))
            call = _UnifiedToolCall(
                name=handler_slug,
                arguments=merged_args,
                target=target,
            )
            handler = self._tool_registry.get_handler(call.name)
            if not handler:
                return ToolResult.fail(f"Local handler '{call.name}' not found")
            try:
                await self._notify_runtime_dispatch(ctx)
                return await handler.execute(ctx, call.arguments)
            except Exception as exc:
                from app.services.runtime_execution_guard_service import RuntimeExecutionGuardError
                if isinstance(exc, RuntimeExecutionGuardError):
                    raise
                return ToolResult.fail(str(exc))

        if target.provider_type == "mcp":
            try:
                merged_args = self._merge_mcp_args(target, operation_call.arguments, ctx, binding=binding)
            except MissingOperationCredentialsError as exc:
                logger.warning(
                    "runtime_mcp_tool_call_blocked_missing_credentials run_id=%s call_id=%s "
                    "operation=%s data_instance_id=%s credential_policy=%s",
                    run_id,
                    call_id,
                    exc.operation,
                    target.data_instance_id,
                    exc.credential_policy,
                )
                return ToolResult.fail(
                    str(exc),
                    error_code="credential_missing",
                    operation=exc.operation,
                    data_instance_id=target.data_instance_id,
                    data_instance_slug=exc.data_instance_slug,
                    required_scope=exc.credential_policy,
                )
            except ValueError as exc:
                credential_context = binding.credential if binding else None
                failure_reason = {
                    "MCP credential broker is required but no data-instance credential is available": "credential_missing",
                    "MCP credential_access could not be issued and raw credential fallback is disabled": "broker_access_not_issued",
                }.get(str(exc), "argument_validation_or_broker_error")
                logger.warning(
                    "runtime_mcp_tool_call_failed run_id=%s call_id=%s operation=%s provider=%s "
                    "data_instance_id=%s stage=credential_argument_build error_type=%s failure_reason=%s "
                    "credential_present=%s credential_id_present=%s credential_id=%s auth_type=%s owner_type=%s "
                    "broker_enabled=%s broker_required=%s raw_fallback_allowed=%s",
                    run_id,
                    call_id,
                    operation_call.tool_name,
                    target.provider_instance_slug or "-",
                    target.data_instance_id or "-",
                    type(exc).__name__,
                    failure_reason,
                    credential_context is not None,
                    bool(credential_context and credential_context.credential_id),
                    credential_context.credential_id if credential_context else "-",
                    credential_context.auth_type if credential_context else "-",
                    credential_context.owner_type if credential_context else "-",
                    self._mcp_credential_broker_enabled,
                    self._mcp_credential_broker_required,
                    self._mcp_allow_raw_credential_fallback,
                )
                return ToolResult.fail(str(exc))
            call = _UnifiedToolCall(
                name=target.mcp_tool_name or "",
                arguments=merged_args,
                target=target,
            )
            return await self._execute_unified_call(call, ctx)

        return ToolResult.fail(f"Unsupported provider type '{target.provider_type}'")

    @staticmethod
    async def _notify_runtime_dispatch(ctx: ToolContext) -> None:
        callback = ctx.extra.get("runtime_operation_dispatch_guard")
        if callback is not None:
            await callback()

    async def _execute_unified_call(self, call: _UnifiedToolCall, ctx: ToolContext) -> ToolResult:
        """
        Unified execution path:
        1) invoke local/remote backend
        2) normalize to MCP-like result payload
        3) map payload to ToolResult
        """
        target = call.target
        call_id = str(ctx.extra.get("runtime_active_tool_call_id") or "")
        run_id = str(ctx.extra.get("run_id") or ctx.extra.get("runtime_run_id") or "")
        instance_context = call.arguments.get("instance_context")
        instance_context = instance_context if isinstance(instance_context, dict) else {}
        credential_access = instance_context.get("credential_access")
        credential_access = credential_access if isinstance(credential_access, dict) else {}
        logger.info(
            "runtime_mcp_tool_call_started run_id=%s call_id=%s operation=%s mcp_tool=%s "
            "provider=%s provider_instance_id=%s data_instance_id=%s target=%s "
            "credential_id=%s auth_type=%s broker_enabled=%s",
            run_id or "-",
            call_id or "-",
            target.operation_slug,
            call.name,
            target.provider_instance_slug or "-",
            target.provider_instance_id or "-",
            target.data_instance_id or "-",
            _safe_url_origin(target.provider_url or ""),
            credential_access.get("credential_id") or "-",
            credential_access.get("auth_type") or instance_context.get("auth_type") or "-",
            self._mcp_credential_broker_enabled,
        )
        try:
            payload = await self._invoke_unified_tool_call(call, ctx)
        except Exception as exc:
            from app.services.runtime_execution_guard_service import RuntimeExecutionGuardError
            if isinstance(exc, RuntimeExecutionGuardError):
                raise
            cause_type, cause_errno, cause_reason = _safe_transport_cause(exc)
            cause_reason = str(safe_diagnostic(cause_reason, secrets=_mcp_call_secrets(call.arguments)))
            logger.warning(
                "runtime_mcp_tool_call_failed run_id=%s call_id=%s operation=%s mcp_tool=%s "
                "provider=%s data_instance_id=%s error_type=%s http_status=%s "
                "cause_type=%s cause_errno=%s cause_reason=%s mcp_diagnostic=%s",
                run_id or "-",
                call_id or "-",
                target.operation_slug,
                call.name,
                target.provider_instance_slug or "-",
                target.data_instance_id or "-",
                type(exc).__name__,
                getattr(exc, "status_code", "-"),
                cause_type,
                cause_errno,
                cause_reason,
                getattr(exc, "mcp_diagnostic", "-"),
            )
            failure = getattr(exc, "mcp_failure", None)
            if not isinstance(failure, dict):
                status_code = getattr(exc, "status_code", None)
                if isinstance(exc, (TimeoutError, httpx.TimeoutException, httpx.ConnectError)) and status_code is None:
                    category = MCPFailureCategory.AVAILABILITY
                else:
                    category = {
                        401: MCPFailureCategory.AUTH,
                        403: MCPFailureCategory.ACCESS,
                        429: MCPFailureCategory.RATE_LIMIT,
                        502: MCPFailureCategory.AVAILABILITY,
                        503: MCPFailureCategory.AVAILABILITY,
                        504: MCPFailureCategory.AVAILABILITY,
                    }.get(status_code, MCPFailureCategory.UNKNOWN)
                cause_type, cause_errno, cause_reason = _safe_transport_cause(exc)
                secrets = _mcp_call_secrets(call.arguments)
                failure = MCPFailure(
                    kind=(MCPFailureKind.HTTP if status_code else
                          MCPFailureKind.PROTOCOL if isinstance(exc, ValueError) else MCPFailureKind.TRANSPORT),
                    category=category,
                    code=f"http_{status_code}" if status_code else type(exc).__name__,
                    message=f"MCP request failed with HTTP {status_code}" if status_code else type(exc).__name__,
                    details=safe_diagnostic({
                        "exception_type": type(exc).__name__,
                        "cause_type": cause_type,
                        "cause_errno": cause_errno,
                        "cause_reason": cause_reason,
                    }, secrets=secrets),
                    request_id=call_id or None,
                    stage="tools_call",
                    http_status=status_code,
                    user_message=_mcp_user_message(category),
                ).bounded_dump()
            failure = MCPFailure.model_validate(failure).bounded_dump()
            return ToolResult.fail(failure["user_message"], mcp_failure=failure, user_message=failure["user_message"])
        result = self._tool_result_from_payload(payload, secrets=_mcp_call_secrets(call.arguments))
        logger.info(
            "runtime_mcp_tool_call_%s run_id=%s call_id=%s operation=%s mcp_tool=%s "
            "provider=%s data_instance_id=%s",
            "completed" if result.success else "failed",
            run_id or "-",
            call_id or "-",
            target.operation_slug,
            call.name,
            target.provider_instance_slug or "-",
            target.data_instance_id or "-",
        )
        return result

    async def _invoke_unified_tool_call(
        self,
        call: _UnifiedToolCall,
        ctx: ToolContext,
    ) -> Dict[str, Any]:
        target = call.target
        if target.provider_type == "local":
            return await self._invoke_local_as_mcp(call, ctx)
        if target.provider_type == "mcp":
            return await self._invoke_remote_mcp(call, ctx)
        raise ValueError(f"Unsupported provider type '{target.provider_type}'")

    async def _invoke_local_as_mcp(self, call: _UnifiedToolCall, ctx: ToolContext) -> Dict[str, Any]:
        handler = self._tool_registry.get_handler(call.name)
        if not handler:
            raise ValueError(f"Local handler '{call.name}' not found")
        result = await handler.execute(ctx, call.arguments)
        if result.success:
            return {
                "isError": False,
                "structuredContent": result.data,
            }
        return {
            "isError": True,
            "content": [{"type": "text", "text": result.error or "Tool execution failed"}],
        }

    async def _invoke_remote_mcp(self, call: _UnifiedToolCall, ctx: ToolContext) -> Dict[str, Any]:
        target = call.target
        if not target.provider_instance_slug:
            raise ValueError(f"MCP provider slug missing for '{target.operation_slug}'")

        provider_url = target.provider_url
        if not provider_url:
            raise ValueError(f"MCP provider URL missing for '{target.operation_slug}'")

        timeout = target.timeout_s or float(ctx.extra.get("runtime_operation_timeout_s") or 300)
        active_call_id = str(ctx.extra.get("runtime_active_tool_call_id") or "").strip()
        request_id = (
            active_call_id
            if re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", active_call_id)
            else uuid.uuid4().hex
        )
        session_id = await self._mcp_initialize(
            provider_url, timeout_s=timeout, request_id=request_id,
            secrets=_mcp_call_secrets(call.arguments),
        )
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": call.name,
                "arguments": call.arguments,
            },
        }
        client = await self._get_client(provider_url, timeout)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session_id,
        }
        headers["x-portal-request-id"] = request_id
        instance_context = call.arguments.get("instance_context")
        instance_context = instance_context if isinstance(instance_context, dict) else {}
        credential_access = instance_context.get("credential_access")
        credential_access = credential_access if isinstance(credential_access, dict) else {}
        logger.info(
            "runtime_mcp_http_request_started request_id=%s run_id=%s stage=tools_call "
            "provider=%s provider_instance_id=%s data_instance_id=%s operation=%s mcp_tool=%s target=%s "
            "credential_access_present=%s credential_id=%s auth_type=%s owner_type=%s",
            request_id,
            str(ctx.extra.get("run_id") or ctx.extra.get("runtime_run_id") or "-"),
            target.provider_instance_slug or "-",
            target.provider_instance_id or "-",
            target.data_instance_id or "-",
            target.operation_slug,
            call.name,
            _safe_url_origin(provider_url),
            bool(credential_access.get("token")),
            credential_access.get("credential_id") or "-",
            credential_access.get("auth_type") or instance_context.get("auth_type") or "-",
            credential_access.get("owner_type") or "-",
        )
        await self._notify_runtime_dispatch(ctx)
        response, attempts = await self._post_with_retry(
            # This is the first point after target resolution, credential
            # merging and MCP initialization where the business operation is
            # about to be sent to the provider.
            client=client,
            provider_url=provider_url,
            headers=headers,
            payload=payload,
            timeout_s=timeout,
            ctx=ctx,
            allow_retries=False,
        )
        if response.status_code in {400, 401, 403, 410}:
            # The result of a tools/call request must never be replayed
            # implicitly. Reinitialize only before a future operation.
            self._mcp_sessions.pop(provider_url, None)
        if response.status_code >= 400:
            logger.warning(
                "runtime_mcp_http_response_error request_id=%s stage=tools_call provider=%s target=%s "
                "http_status=%s attempts=%s",
                request_id,
                target.provider_instance_slug or "-",
                _safe_url_origin(provider_url),
                response.status_code,
                attempts,
            )
            category = {
                401: MCPFailureCategory.AUTH,
                403: MCPFailureCategory.ACCESS,
                429: MCPFailureCategory.RATE_LIMIT,
                502: MCPFailureCategory.AVAILABILITY,
                503: MCPFailureCategory.AVAILABILITY,
                504: MCPFailureCategory.AVAILABILITY,
            }.get(response.status_code, MCPFailureCategory.UNKNOWN)
            response_body = response.content[:24000]
            try:
                source_diagnostic: Any = json.loads(response_body) if response_body else None
            except (ValueError, UnicodeDecodeError):
                source_diagnostic = response_body.decode("utf-8", errors="replace")
            if len(response.content) > len(response_body):
                source_diagnostic = {"body": source_diagnostic, "_truncated": True}
            secrets = _mcp_call_secrets(call.arguments)
            error = ValueError(_mcp_user_message(category))
            error.mcp_failure = MCPFailure(
                kind=MCPFailureKind.HTTP,
                category=category,
                code=f"http_{response.status_code}",
                message=f"MCP HTTP request failed with status {response.status_code}",
                details=safe_diagnostic({"attempts": attempts, "source_response": source_diagnostic}, secrets=secrets),
                rpc_data=safe_diagnostic(source_diagnostic, secrets=secrets),
                request_id=request_id,
                stage="tools_call",
                http_status=response.status_code,
                user_message=_mcp_user_message(category),
            ).bounded_dump()
            raise error
        try:
            data = _parse_mcp_response_body(response.text)
        except Exception as exc:
            raise MCPFailureError(MCPFailure(
                kind=MCPFailureKind.PROTOCOL,
                category=MCPFailureCategory.UNKNOWN,
                code=type(exc).__name__,
                message="MCP source returned an invalid response",
                details={"exception_type": type(exc).__name__},
                request_id=request_id,
                stage="tools_call",
                user_message=_mcp_user_message(MCPFailureCategory.UNKNOWN),
            ).bounded_dump()) from exc
        rpc_error = data.get("error") if isinstance(data.get("error"), dict) else {}
        logger.info(
            "runtime_mcp_http_response_received request_id=%s stage=tools_call provider=%s target=%s "
            "http_status=%s attempts=%s rpc_code=%s",
            request_id,
            target.provider_instance_slug or "-",
            _safe_url_origin(provider_url),
            response.status_code,
            attempts,
            rpc_error.get("code", "-") if rpc_error and isinstance(rpc_error.get("code"), int) and not isinstance(rpc_error.get("code"), bool) else "invalid_code" if rpc_error else "-",
        )
        return self._mcp_tool_result_or_raise(data, secrets=_mcp_call_secrets(call.arguments))

    @staticmethod
    def _mcp_tool_result_or_raise(
        response_payload: Dict[str, Any], *, secrets: tuple[str, ...] = (),
    ) -> Dict[str, Any]:
        """Return a valid MCP tools/call result or surface its JSON-RPC error.

        MCP servers commonly keep HTTP 200 for protocol-level errors.  Treating
        an absent ``result`` as an empty object turns authentication, broker and
        provider failures into false successful tool calls.
        """
        error = response_payload.get("error")
        if isinstance(error, dict):
            data = error.get("data")
            try:
                failure = normalize_failure(data, secrets=secrets)
                if failure is None:
                    raise ValueError("unsupported MCP failure envelope")
            except Exception:
                message = str(safe_diagnostic(error.get("message") or "MCP RPC error", secrets=secrets))
                is_invalid_params = error.get("code") == -32602
                category = MCPFailureCategory.INPUT if is_invalid_params else MCPFailureCategory.UNKNOWN
                failure = MCPFailure(
                    kind=MCPFailureKind.RPC,
                    category=category,
                    code=safe_diagnostic(error.get("code"), secrets=secrets) if error.get("code") is not None else None,
                    message=message,
                    details=safe_diagnostic(data, secrets=secrets),
                    rpc_code=safe_diagnostic(error.get("code"), secrets=secrets),
                    rpc_data=safe_diagnostic(data, secrets=secrets),
                    user_message=_mcp_user_message(category),
                ).bounded_dump()
            return {
                "isError": True,
                "content": [{"type": "text", "text": failure["message"]}],
                "_meta": {"portal.failure": failure},
            }
        if error:
            raise ValueError("MCP tool call failed: MCP RPC error")

        result = response_payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("Invalid MCP tools/call response: missing result object")
        return result

    @staticmethod
    def _tool_result_from_payload(payload: Dict[str, Any], *, secrets: tuple[str, ...] = ()) -> ToolResult:
        if payload.get("isError"):
            meta = payload.get("_meta") if isinstance(payload.get("_meta"), dict) else {}
            raw_failure = meta.get("portal.failure")
            try:
                failure = normalize_failure(raw_failure, secrets=secrets)
                if failure is None:
                    raise ValueError("unsupported MCP failure envelope")
            except Exception:
                content = payload.get("content") or []
                message = _extract_mcp_error_message(content) or "MCP tool reported an error"
                failure = MCPFailure(
                    kind=MCPFailureKind.TOOL,
                    category=MCPFailureCategory.UNKNOWN,
                    code="tool_error",
                    message=str(safe_diagnostic(message, secrets=secrets)),
                    details=safe_diagnostic({"content": content, "structuredContent": payload.get("structuredContent")}, secrets=secrets),
                    user_message=_mcp_user_message(MCPFailureCategory.UNKNOWN),
                ).bounded_dump()
            return ToolResult.fail(failure["user_message"], mcp_failure=failure, user_message=failure["user_message"])

        structured = payload.get("structuredContent")
        if "structuredContent" in payload:
            content = payload.get("content") or []
            extras = _meaningful_mcp_content(content, structured)
            return ToolResult.ok(structured, **({"mcp_content": safe_diagnostic(extras, secrets=secrets)} if extras else {}))

        content = payload.get("content") or []
        text = _extract_mcp_text_content(content)
        if len(content) == 1 and content[0].get("type") == "text":
            try:
                return ToolResult.ok(json.loads(text))
            except (ValueError, TypeError):
                pass
        return ToolResult.ok({"content": text, "raw": payload})

    @staticmethod
    def _merge_local_args(
        target: ProviderExecutionTarget,
        args: Dict[str, Any],
        ctx: ToolContext,
        *,
        binding: Optional[OperationExecutionBinding] = None,
    ) -> Dict[str, Any]:
        merged_args = dict(args)
        if binding is None:
            return merged_args
        instance_info = binding.context.model_dump()
        request_slug = merged_args.get("collection_slug")
        binding_collection_slug = instance_info.get("collection_slug")
        if binding_collection_slug:
            if not request_slug:
                raise ValueError("collection_slug is required for a collection operation")
            if request_slug != binding_collection_slug:
                raise ValueError(
                    f"Collection '{request_slug}' does not match operation target "
                    f"'{binding_collection_slug}'."
                )
        merged_args.pop("collection_id", None)

        return merged_args

    def _merge_mcp_args(
        self,
        target: ProviderExecutionTarget,
        args: Dict[str, Any],
        ctx: ToolContext,
        *,
        binding: Optional[OperationExecutionBinding] = None,
    ) -> Dict[str, Any]:
        merged_args = dict(args)
        if binding is None:
            return merged_args
        instance_info = binding.context.model_dump()
        data_config = binding.context.config or {}
        credential_context = binding.credential
        run_id = str(ctx.extra.get("run_id") or ctx.extra.get("runtime_run_id") or "-")
        call_id = str(ctx.extra.get("runtime_active_tool_call_id") or "-")
        request_slug = merged_args.get("collection_slug")
        binding_collection_slug = instance_info.get("collection_slug")
        if binding_collection_slug:
            if not request_slug:
                raise ValueError("collection_slug is required for a collection operation")
            if request_slug != binding_collection_slug:
                raise ValueError(
                    f"Collection '{request_slug}' does not match operation target "
                    f"'{binding_collection_slug}'."
                )
        merged_args.pop("collection_id", None)

        supplied_context = merged_args.get("instance_context")
        context_was_malformed = supplied_context is not None and not isinstance(supplied_context, dict)
        instance_context = dict(supplied_context) if isinstance(supplied_context, dict) else {}
        supplied_internal_fields = {
            "top_level_credential_access": "credential_access" in merged_args,
            "top_level_credentials": "credentials" in merged_args,
            "nested_credential_access": "credential_access" in instance_context,
            "nested_credentials": "credentials" in instance_context,
        }
        for key in ("credential_access", "credentials"):
            merged_args.pop(key, None)
            instance_context.pop(key, None)
        # auth_type is runtime-owned metadata too; never trust a caller-provided value.
        instance_context.pop("auth_type", None)
        if context_was_malformed or any(supplied_internal_fields.values()):
            logger.warning(
                "runtime_mcp_untrusted_credential_arguments_sanitized run_id=%s call_id=%s operation=%s "
                "data_instance_id=%s context_was_malformed=%s top_level_access_present=%s "
                "top_level_credentials_present=%s nested_access_present=%s nested_credentials_present=%s",
                run_id,
                call_id,
                target.operation_slug,
                target.data_instance_id or "-",
                context_was_malformed,
                supplied_internal_fields["top_level_credential_access"],
                supplied_internal_fields["top_level_credentials"],
                supplied_internal_fields["nested_credential_access"],
                supplied_internal_fields["nested_credentials"],
            )

        instance_context.update(
            {
                "data_instance_slug": target.data_instance_slug,
                "data_instance_id": target.data_instance_id,
                "provider_instance_slug": target.provider_instance_slug,
                "provider_instance_id": target.provider_instance_id,
                "config": data_config,
                "domain": instance_info.get("domain"),
                "data_instance_url": instance_info.get("data_instance_url"),
                "provider_url": instance_info.get("provider_url"),
            }
        )
        if credential_context:
            instance_context["auth_type"] = credential_context.auth_type
            access_ctx = self._build_mcp_credential_access_context(
                target=target,
                credential_context=credential_context,
                ctx=ctx,
            )
            if access_ctx:
                instance_context["credential_access"] = access_ctx
                logger.info(
                    "runtime_mcp_credential_access_built run_id=%s call_id=%s operation=%s "
                    "data_instance_id=%s provider_instance_id=%s credential_id=%s auth_type=%s "
                    "owner_type=%s broker_enabled=%s access_token_present=true",
                    run_id,
                    call_id,
                    target.operation_slug,
                    target.data_instance_id or "-",
                    target.provider_instance_id or "-",
                    credential_context.credential_id or "-",
                    credential_context.auth_type or "-",
                    credential_context.owner_type or "-",
                    self._mcp_credential_broker_enabled,
                )
            elif self._mcp_allow_raw_credential_fallback and credential_context.payload:
                # Explicitly local-only legacy mode.
                logger.warning(
                    "runtime_mcp_raw_credential_fallback_used run_id=%s call_id=%s "
                    "operation=%s credential_id=%s",
                    run_id, call_id, target.operation_slug, credential_context.credential_id or "-",
                )
                instance_context["credentials"] = credential_context.payload
            else:
                raise ValueError(
                    "MCP credential_access could not be issued and raw credential fallback is disabled"
                )
        elif target.credential_policy != "not_required":
            raise MissingOperationCredentialsError(
                operation=target.mcp_tool_name or target.operation_slug,
                data_instance_slug=target.data_instance_slug,
                credential_policy=target.credential_policy,
            )

        merged_args["instance_context"] = instance_context

        # Provider routing and credentials live only in instance_context.
        # Public arguments such as url/address/token may belong to the tool.
        return merged_args

    @staticmethod
    def _resolve_target_binding(
        operation_slug: str,
        ctx: ToolContext,
    ) -> tuple[Optional[OperationExecutionBinding], Optional[ProviderExecutionTarget]]:
        deps = ctx.get_runtime_deps()
        graph_raw = deps.execution_graph
        if not graph_raw:
            return None, None
        graph = (
            graph_raw
            if isinstance(graph_raw, RuntimeExecutionGraph)
            else RuntimeExecutionGraph.model_validate(graph_raw)
        )
        binding = graph.get(operation_slug)
        if not binding:
            return None, None
        return binding, binding.target

    def _build_mcp_credential_access_context(
        self,
        *,
        target: ProviderExecutionTarget,
        credential_context: OperationCredentialContext,
        ctx: ToolContext,
    ) -> Optional[Dict[str, Any]]:
        reason = (
            "broker_disabled" if not self._mcp_credential_broker_enabled
            else "credential_id_missing" if not credential_context.credential_id
            else None
        )
        if reason:
            logger.warning(
                "runtime_mcp_credential_access_not_issued run_id=%s call_id=%s operation=%s "
                "data_instance_id=%s provider_instance_id=%s user_id=%s tenant_id=%s "
                "credential_id=%s auth_type=%s owner_type=%s policy=%s "
                "broker_enabled=%s broker_required=%s raw_fallback_allowed=%s "
                "payload_present=%s expected_delivery=credential_access reason=%s",
                ctx.extra.get("run_id") or ctx.extra.get("runtime_run_id") or "-",
                ctx.extra.get("runtime_active_tool_call_id") or "-",
                target.operation_slug, target.data_instance_id, target.provider_instance_id,
                ctx.user_id, ctx.tenant_id, credential_context.credential_id or "-",
                credential_context.auth_type, credential_context.owner_type,
                target.credential_policy, self._mcp_credential_broker_enabled,
                self._mcp_credential_broker_required, self._mcp_allow_raw_credential_fallback,
                bool(credential_context.payload), reason,
            )
            return None

        access_ctx = MCPCredentialBrokerService.issue_access_context(
            user_id=ctx.user_id,
            tenant_id=ctx.tenant_id,
            provider_instance_id=target.provider_instance_id,
            provider_instance_slug=target.provider_instance_slug,
            data_instance_id=target.data_instance_id,
            data_instance_slug=target.data_instance_slug,
            operation_slug=target.operation_slug,
            mcp_tool_name=target.mcp_tool_name,
            credential_id=credential_context.credential_id,
            auth_type=credential_context.auth_type,
            owner_type=credential_context.owner_type or "unknown",
        )
        return {
            "token": access_ctx.token,
            "resolve_url": access_ctx.resolve_url,
            "credential_id": access_ctx.credential_id,
            "auth_type": access_ctx.auth_type,
            "owner_type": access_ctx.owner_type,
            "expires_at": access_ctx.expires_at,
        }

    async def _mcp_initialize(
        self, provider_url: str, timeout_s: Optional[int], request_id: str = "",
        secrets: tuple[str, ...] = (),
    ) -> str:
        now = time.monotonic()
        cached = self._mcp_sessions.get(provider_url)
        if cached and cached[1] > now:
            return cached[0]

        async with self._mcp_session_lock:
            cached = self._mcp_sessions.get(provider_url)
            if cached and cached[1] > time.monotonic():
                return cached[0]

            session_id = await self._mcp_initialize_fresh(
                provider_url, timeout_s, request_id=request_id, secrets=secrets,
            )
            self._mcp_sessions[provider_url] = (session_id, time.monotonic() + self._mcp_session_ttl_s)
            return session_id

    async def _mcp_initialize_fresh(
        self, provider_url: str, timeout_s: Optional[int], request_id: str = "",
        secrets: tuple[str, ...] = (),
    ) -> str:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ml-portal", "version": "1.0"},
            },
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "x-portal-request-id": request_id or uuid.uuid4().hex,
        }
        timeout = timeout_s or 30
        client = await self._get_client(provider_url, timeout)
        try:
            response, _ = await self._post_with_retry(
                client=client,
                provider_url=provider_url,
                headers=headers,
                payload=payload,
                timeout_s=timeout,
            )
        except httpx.HTTPError as exc:
            category = (
                MCPFailureCategory.AVAILABILITY
                if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))
                else MCPFailureCategory.UNKNOWN
            )
            raise MCPFailureError(MCPFailure(
                kind=MCPFailureKind.TRANSPORT,
                category=category,
                code=type(exc).__name__,
                message=type(exc).__name__,
                details={"exception_type": type(exc).__name__},
                request_id=headers["x-portal-request-id"],
                stage="initialize",
                user_message=_mcp_user_message(category),
            ).bounded_dump()) from exc
        if response.status_code >= 400:
            logger.warning(
                "runtime_mcp_http_response_error request_id=%s stage=initialize target=%s http_status=%s",
                headers["x-portal-request-id"],
                _safe_url_origin(provider_url),
                response.status_code,
            )
            category = {
                401: MCPFailureCategory.AUTH,
                403: MCPFailureCategory.ACCESS,
                429: MCPFailureCategory.RATE_LIMIT,
                502: MCPFailureCategory.AVAILABILITY,
                503: MCPFailureCategory.AVAILABILITY,
                504: MCPFailureCategory.AVAILABILITY,
            }.get(response.status_code, MCPFailureCategory.UNKNOWN)
            body = response.content[:24000]
            try:
                source_details: Any = json.loads(body) if body else None
            except (ValueError, UnicodeDecodeError):
                source_details = body.decode("utf-8", errors="replace")
            if len(response.content) > len(body):
                source_details = {"body": source_details, "_truncated": True}
            raise MCPFailureError(MCPFailure(
                kind=MCPFailureKind.HTTP,
                category=category,
                code=f"http_{response.status_code}",
                message=f"MCP initialize returned HTTP {response.status_code}",
                details=safe_diagnostic(source_details, secrets=secrets),
                request_id=headers["x-portal-request-id"],
                stage="initialize",
                http_status=response.status_code,
                user_message=_mcp_user_message(category),
            ).bounded_dump())
        try:
            initialize_payload = _parse_mcp_response_body(response.text)
        except Exception as exc:
            raise MCPFailureError(MCPFailure(
                kind=MCPFailureKind.PROTOCOL,
                category=MCPFailureCategory.UNKNOWN,
                code=type(exc).__name__,
                message="MCP initialize returned an invalid response",
                details={"exception_type": type(exc).__name__},
                request_id=headers["x-portal-request-id"],
                stage="initialize",
                user_message=_mcp_user_message(MCPFailureCategory.UNKNOWN),
            ).bounded_dump()) from exc
        rpc_error = initialize_payload.get("error")
        if isinstance(rpc_error, dict):
            category = MCPFailureCategory.INPUT if rpc_error.get("code") == -32602 else MCPFailureCategory.UNKNOWN
            failure = normalize_failure(rpc_error.get("data"), secrets=secrets)
            if failure is None:
                failure = MCPFailure(
                    kind=MCPFailureKind.RPC,
                    category=category,
                    code=safe_diagnostic(rpc_error.get("code"), secrets=secrets) if rpc_error.get("code") is not None else None,
                    message=str(safe_diagnostic(rpc_error.get("message") or "MCP initialization failed", secrets=secrets)),
                    details=safe_diagnostic(rpc_error.get("data"), secrets=secrets),
                    request_id=headers["x-portal-request-id"],
                    stage="initialize",
                    rpc_code=safe_diagnostic(rpc_error.get("code"), secrets=secrets),
                    rpc_data=safe_diagnostic(rpc_error.get("data"), secrets=secrets),
                    user_message=_mcp_user_message(category),
                ).bounded_dump()
            raise MCPFailureError(failure)
        if not isinstance(initialize_payload.get("result"), dict):
            raise MCPFailureError(MCPFailure(
                kind=MCPFailureKind.PROTOCOL,
                category=MCPFailureCategory.UNKNOWN,
                code="missing_initialize_result",
                message="MCP initialize response has no result object",
                details=safe_diagnostic(initialize_payload, secrets=secrets),
                request_id=headers["x-portal-request-id"],
                stage="initialize",
                user_message=_mcp_user_message(MCPFailureCategory.UNKNOWN),
            ).bounded_dump())
        session_id = response.headers.get("mcp-session-id")
        if not session_id:
            raise MCPFailureError(MCPFailure(
                kind=MCPFailureKind.PROTOCOL,
                category=MCPFailureCategory.UNKNOWN,
                code="missing_session_id",
                message="MCP initialize response has no session identifier",
                details={"http_status": response.status_code},
                request_id=headers["x-portal-request-id"],
                stage="initialize",
                http_status=response.status_code,
                user_message=_mcp_user_message(MCPFailureCategory.UNKNOWN),
            ).bounded_dump())
        logger.info(
            "runtime_mcp_http_response_received request_id=%s stage=initialize target=%s http_status=%s session_received=true",
            headers["x-portal-request-id"],
            _safe_url_origin(provider_url),
            response.status_code,
        )
        return session_id

    async def _get_client(self, provider_url: str, timeout_s: int) -> httpx.AsyncClient:
        existing = self._clients.get(provider_url)
        if existing is not None:
            return existing

        async with self._client_lock:
            existing = self._clients.get(provider_url)
            if existing is not None:
                return existing
            client = httpx.AsyncClient(timeout=timeout_s, verify=outbound_http_verify())
            self._clients[provider_url] = client
            return client

    async def _post_with_retry(
        self,
        *,
        client: httpx.AsyncClient,
        provider_url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        timeout_s: int,
        ctx: Optional[ToolContext] = None,
        allow_retries: bool = True,
    ) -> tuple[httpx.Response, int]:
        # A tools/call POST may have committed a write even when the response
        # is lost. Callers must opt in only when the request is idempotent.
        max_attempts = (self._http_max_retries if allow_retries else 0) + 1
        last_response: Optional[httpx.Response] = None
        last_exception: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                request_id = headers.get("x-portal-request-id", "-")
                stage = str(payload.get("method") or "mcp_request")
                logger.info(
                    "runtime_mcp_http_attempt_started request_id=%s stage=%s target=%s attempt=%s/%s",
                    request_id,
                    stage,
                    _safe_url_origin(provider_url),
                    attempt,
                    max_attempts,
                )
                response = await client.post(provider_url, headers=headers, json=payload)
                last_response = response
                logger.info(
                    "runtime_mcp_http_attempt_response request_id=%s stage=%s target=%s attempt=%s/%s "
                    "http_status=%s response_bytes=%s content_type=%s",
                    request_id,
                    stage,
                    _safe_url_origin(provider_url),
                    attempt,
                    max_attempts,
                    response.status_code,
                    len(response.content),
                    response.headers.get("content-type", "-"),
                )
                if not self._is_retryable_status(response.status_code) or attempt == max_attempts:
                    return response, attempt
            except Exception as exc:
                last_exception = exc
                cause_type, cause_errno, cause_reason = _safe_transport_cause(exc)
                logger.warning(
                    "runtime_mcp_http_attempt_failed request_id=%s stage=%s target=%s attempt=%s/%s "
                    "error_type=%s cause_type=%s cause_errno=%s cause_reason=%s",
                    headers.get("x-portal-request-id", "-"),
                    str(payload.get("method") or "mcp_request"),
                    _safe_url_origin(provider_url),
                    attempt,
                    max_attempts,
                    type(exc).__name__,
                    cause_type,
                    cause_errno,
                    cause_reason,
                )
                if not self._is_retryable_exception(exc) or attempt == max_attempts:
                    raise

            delay_ms = int(self._retry_delay_seconds(attempt) * 1000)
            await self._emit_retry(ctx, attempt=attempt, max_attempts=max_attempts, delay_ms=delay_ms)
            await asyncio.sleep(delay_ms / 1000)

        if last_response is not None:
            return last_response, max_attempts
        if last_exception is not None:
            raise last_exception
        raise RuntimeError("MCP request failed without response")

    async def _emit_retry(
        self,
        ctx: Optional[ToolContext],
        *,
        attempt: int,
        max_attempts: int,
        delay_ms: int,
    ) -> None:
        if ctx is None:
            return
        sink = ctx.extra.get("runtime_event_logger")
        call_id = ctx.extra.get("runtime_active_tool_call_id")
        if sink is None or not call_id:
            return
        await sink.emit(
            RuntimeEvent(
                RuntimeEventType.PROTOCOL_RETRY,
                {
                    "entity_type": "tool_call",
                    "entity_id": str(call_id),
                    "call_id": str(call_id),
                    "tool": str(ctx.extra.get("runtime_active_tool_slug") or "operation"),
                    "parent_entity_type": "agent_execution",
                    "parent_entity_id": str(ctx.extra.get("run_id") or ""),
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "reason": "provider_retry",
                    "retry_delay_ms": delay_ms,
                },
            ),
            phase=OrchestrationPhase.AGENT,
        )

    def _retry_delay_seconds(self, attempt: int) -> float:
        return (self._retry_base_delay_ms * (2 ** (attempt - 1))) / 1000.0

    @staticmethod
    def _is_retryable_status(status_code: int) -> bool:
        return status_code in {408, 409, 425, 429, 500, 502, 503, 504}

    @staticmethod
    def _is_retryable_exception(exc: Exception) -> bool:
        return isinstance(
            exc,
            (
                httpx.ConnectError,
                httpx.ReadError,
                httpx.ReadTimeout,
                httpx.WriteError,
                httpx.WriteTimeout,
                httpx.RemoteProtocolError,
                httpx.PoolTimeout,
            ),
        )


def _extract_mcp_text_content(content: List[Dict[str, Any]]) -> str:
    texts: List[str] = []
    for item in content:
        text = item.get("text")
        if isinstance(text, str) and text:
            texts.append(text)
    return "\n".join(texts)


def _meaningful_mcp_content(content: Any, structured: Any) -> dict[str, Any]:
    """Retain bounded MCP annotations/resources with an explicit loss receipt."""
    if not isinstance(content, list):
        return {"items": [], "original_count": 0, "omitted_count": 0, "truncated": False,
                "duplicate_count": 0, "warning_summaries": [], "warnings_omitted": 0}
    canonical = None
    try:
        canonical = json.dumps(structured, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        pass
    extras: list[dict[str, Any]] = []
    warning_summaries: list[str] = []
    warning_count = 0
    duplicate_count = 0
    for item in content:
        if not isinstance(item, dict):
            continue
        text_value = item.get("text")
        if isinstance(text_value, str) and re.search(r"(?i)\b(warning|error|failed|failure|truncated|omitted)\b", text_value):
            warning_count += 1
            if len(warning_summaries) < 20:
                warning_summaries.append(text_value[:1000])
        if isinstance(text_value, str) and canonical is not None:
            try:
                if json.dumps(json.loads(text_value), ensure_ascii=False, sort_keys=True, separators=(",", ":")) == canonical:
                    duplicate_count += 1
                    continue
            except (ValueError, TypeError):
                pass
        extras.append(item)
    selected = extras[:50]
    omitted = max(0, len(extras) - len(selected))
    return {"items": selected, "original_count": len(content), "omitted_count": omitted,
            "duplicate_count": duplicate_count, "truncated": omitted > 0,
            "warning_summaries": warning_summaries,
            "warnings_omitted": max(0, warning_count - len(warning_summaries))}


def _extract_mcp_error_message(content: List[Dict[str, Any]]) -> Optional[str]:
    text = _extract_mcp_text_content(content)
    return text or None
