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


@dataclass(slots=True)
class _UnifiedToolCall:
    """Normalized runtime tool call (local and remote share this shape)."""

    name: str
    arguments: Dict[str, Any]
    target: ProviderExecutionTarget


class DirectOperationExecutor:
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
                return await handler.execute(ctx, call.arguments)
            except Exception as exc:
                return ToolResult.fail(str(exc))

        if target.provider_type == "mcp":
            try:
                merged_args = self._merge_mcp_args(target, operation_call.arguments, ctx, binding=binding)
            except ValueError as exc:
                logger.warning(
                    "runtime_mcp_tool_call_failed run_id=%s call_id=%s operation=%s provider=%s "
                    "data_instance_id=%s stage=credential_argument_build error_type=%s",
                    run_id,
                    call_id,
                    operation_call.tool_name,
                    target.provider_instance_slug or "-",
                    target.data_instance_id or "-",
                    type(exc).__name__,
                )
                return ToolResult.fail(str(exc))
            call = _UnifiedToolCall(
                name=target.mcp_tool_name or "",
                arguments=merged_args,
                target=target,
            )
            return await self._execute_unified_call(call, ctx)

        return ToolResult.fail(f"Unsupported provider type '{target.provider_type}'")

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
            cause_type, cause_errno, cause_reason = _safe_transport_cause(exc)
            logger.warning(
                "runtime_mcp_tool_call_failed run_id=%s call_id=%s operation=%s mcp_tool=%s "
                "provider=%s data_instance_id=%s error_type=%s http_status=%s "
                "cause_type=%s cause_errno=%s cause_reason=%s",
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
            )
            return ToolResult.fail(str(exc))
        result = self._tool_result_from_payload(payload)
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
        session_id = await self._mcp_initialize(provider_url, timeout_s=timeout, request_id=request_id)
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
        logger.info(
            "runtime_mcp_http_request_started request_id=%s run_id=%s stage=tools_call "
            "provider=%s provider_instance_id=%s data_instance_id=%s operation=%s mcp_tool=%s target=%s",
            request_id,
            str(ctx.extra.get("run_id") or ctx.extra.get("runtime_run_id") or "-"),
            target.provider_instance_slug or "-",
            target.provider_instance_id or "-",
            target.data_instance_id or "-",
            target.operation_slug,
            call.name,
            _safe_url_origin(provider_url),
        )
        response, attempts = await self._post_with_retry(
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
            raise ValueError(
                f"MCP tool call failed with HTTP {response.status_code} after {attempts} attempts"
            )
        data = _parse_mcp_response_body(response.text)
        rpc_error = data.get("error") if isinstance(data.get("error"), dict) else {}
        logger.info(
            "runtime_mcp_http_response_received request_id=%s stage=tools_call provider=%s target=%s "
            "http_status=%s attempts=%s rpc_code=%s",
            request_id,
            target.provider_instance_slug or "-",
            _safe_url_origin(provider_url),
            response.status_code,
            attempts,
            rpc_error.get("code", "-") if rpc_error else "-",
        )
        return self._mcp_tool_result_or_raise(data)

    @staticmethod
    def _mcp_tool_result_or_raise(response_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Return a valid MCP tools/call result or surface its JSON-RPC error.

        MCP servers commonly keep HTTP 200 for protocol-level errors.  Treating
        an absent ``result`` as an empty object turns authentication, broker and
        provider failures into false successful tool calls.
        """
        error = response_payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "MCP RPC error")
            code = error.get("code")
            suffix = f" (code {code})" if code is not None else ""
            raise ValueError(f"MCP tool call failed{suffix}: {message}")
        if error:
            raise ValueError("MCP tool call failed: MCP RPC error")

        result = response_payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("Invalid MCP tools/call response: missing result object")
        return result

    @staticmethod
    def _tool_result_from_payload(payload: Dict[str, Any]) -> ToolResult:
        if payload.get("isError"):
            content = payload.get("content") or []
            message = _extract_mcp_error_message(content) or "Tool call failed"
            return ToolResult.fail(message)

        structured = payload.get("structuredContent")
        if "structuredContent" in payload:
            return ToolResult.ok(structured)

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

        merged_args.setdefault("instance_context", {})
        if isinstance(merged_args["instance_context"], dict):
            merged_args["instance_context"].update(
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
                merged_args["instance_context"]["auth_type"] = credential_context.auth_type
                access_ctx = self._build_mcp_credential_access_context(
                    target=target,
                    credential_context=credential_context,
                    ctx=ctx,
                )
                if access_ctx:
                    merged_args["instance_context"]["credential_access"] = access_ctx
                elif self._mcp_allow_raw_credential_fallback and credential_context.payload:
                    # Explicitly local-only legacy mode.
                    merged_args["instance_context"]["credentials"] = credential_context.payload
                else:
                    raise ValueError(
                        "MCP credential_access could not be issued and raw credential fallback is disabled"
                    )
            elif self._mcp_credential_broker_required:
                raise ValueError("MCP credential broker is required but no data-instance credential is available")

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
        if not self._mcp_credential_broker_enabled:
            return None
        if not credential_context.credential_id:
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
    ) -> str:
        now = time.monotonic()
        cached = self._mcp_sessions.get(provider_url)
        if cached and cached[1] > now:
            return cached[0]

        async with self._mcp_session_lock:
            cached = self._mcp_sessions.get(provider_url)
            if cached and cached[1] > time.monotonic():
                return cached[0]

            session_id = await self._mcp_initialize_fresh(provider_url, timeout_s, request_id=request_id)
            self._mcp_sessions[provider_url] = (session_id, time.monotonic() + self._mcp_session_ttl_s)
            return session_id

    async def _mcp_initialize_fresh(
        self, provider_url: str, timeout_s: Optional[int], request_id: str = "",
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
        response, _ = await self._post_with_retry(
            client=client,
            provider_url=provider_url,
            headers=headers,
            payload=payload,
            timeout_s=timeout,
        )
        if response.status_code >= 400:
            logger.warning(
                "runtime_mcp_http_response_error request_id=%s stage=initialize target=%s http_status=%s",
                headers["x-portal-request-id"],
                _safe_url_origin(provider_url),
                response.status_code,
            )
            raise ValueError(f"MCP initialize failed with HTTP {response.status_code}")
        session_id = response.headers.get("mcp-session-id")
        if not session_id:
            raise ValueError("MCP initialize response missing mcp-session-id")
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


def _extract_mcp_error_message(content: List[Dict[str, Any]]) -> Optional[str]:
    text = _extract_mcp_text_content(content)
    return text or None
