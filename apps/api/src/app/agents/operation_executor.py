from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from app.agents.context import OperationCall, ToolContext, ToolResult
from app.agents.contracts import OperationCredentialContext, ProviderExecutionTarget
from app.agents.registry import ToolRegistry
from app.agents.runtime_graph import OperationExecutionBinding, RuntimeExecutionGraph
from app.core.config import get_settings
from app.services.mcp_credential_broker_service import MCPCredentialBrokerService
from app.services.mcp_jsonrpc_client import parse_mcp_response as _parse_mcp_response_body


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
        self._mcp_credential_broker_enabled = bool(
            getattr(settings, "MCP_CREDENTIAL_BROKER_ENABLED", False)
        )
        env_name = str(getattr(settings, "ENV", "local") or "local").strip().lower()
        self._mcp_credential_broker_required = bool(
            getattr(settings, "MCP_CREDENTIAL_BROKER_REQUIRED", False)
            or env_name not in {"local", "development", "dev"}
        )
        self._mcp_allow_raw_credential_fallback = bool(
            getattr(settings, "MCP_ALLOW_RAW_CREDENTIAL_FALLBACK", False)
        )

    async def execute(self, operation_call: OperationCall, ctx: ToolContext) -> ToolResult:
        binding, target = self._resolve_target_binding(operation_call.operation_slug, ctx)
        if not target:
            return ToolResult.fail(f"Execution target not found for '{operation_call.operation_slug}'")

        if target.provider_type == "local":
            handler_slug = target.handler_slug
            if not handler_slug:
                return ToolResult.fail(
                    f"Local handler missing for '{operation_call.operation_slug}'"
                )
            merged_args = self._merge_local_args(target, operation_call.arguments, ctx, binding=binding)
            call = _UnifiedToolCall(
                name=handler_slug,
                arguments=merged_args,
                target=target,
            )
            return await self._execute_unified_call(call, ctx)

        if target.provider_type == "mcp":
            try:
                merged_args = self._merge_mcp_args(target, operation_call.arguments, ctx, binding=binding)
            except ValueError as exc:
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
        try:
            payload = await self._invoke_unified_tool_call(call, ctx)
        except Exception as exc:
            return ToolResult.fail(str(exc))
        return self._tool_result_from_payload(payload)

    async def _invoke_unified_tool_call(
        self,
        call: _UnifiedToolCall,
        ctx: ToolContext,
    ) -> Dict[str, Any]:
        target = call.target
        if target.provider_type == "local":
            return await self._invoke_local_as_mcp(call, ctx)
        if target.provider_type == "mcp":
            return await self._invoke_remote_mcp(call)
        raise ValueError(f"Unsupported provider type '{target.provider_type}'")

    async def _invoke_local_as_mcp(self, call: _UnifiedToolCall, ctx: ToolContext) -> Dict[str, Any]:
        handler = self._tool_registry.get_handler(call.name)
        if not handler:
            raise ValueError(f"Local handler '{call.name}' not found")
        result = await handler.execute(ctx, call.arguments)
        if result.success:
            return {
                "isError": False,
                "structuredContent": result.data or {},
            }
        return {
            "isError": True,
            "content": [{"type": "text", "text": result.error or "Tool execution failed"}],
        }

    async def _invoke_remote_mcp(self, call: _UnifiedToolCall) -> Dict[str, Any]:
        target = call.target
        if not target.provider_instance_slug:
            raise ValueError(f"MCP provider slug missing for '{target.operation_slug}'")

        provider_url = target.provider_url
        if not provider_url:
            raise ValueError(f"MCP provider URL missing for '{target.operation_slug}'")

        session_id = await self._mcp_initialize(provider_url, timeout_s=target.timeout_s)
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": call.name,
                "arguments": call.arguments,
            },
        }
        timeout = target.timeout_s or 30
        client = await self._get_client(provider_url, timeout)
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session_id,
        }
        response, attempts = await self._post_with_retry(
            client=client,
            provider_url=provider_url,
            headers=headers,
            payload=payload,
            timeout_s=timeout,
        )
        if response.status_code in {400, 401, 403, 410}:
            self._mcp_sessions.pop(provider_url, None)
            session_id = await self._mcp_initialize_fresh(provider_url, timeout_s=target.timeout_s)
            async with self._mcp_session_lock:
                self._mcp_sessions[provider_url] = (session_id, time.monotonic() + self._mcp_session_ttl_s)
            headers["mcp-session-id"] = session_id
            response, attempts = await self._post_with_retry(
                client=client,
                provider_url=provider_url,
                headers=headers,
                payload=payload,
                timeout_s=timeout,
            )
        if response.status_code >= 400:
            raise ValueError(
                f"MCP tool call failed with HTTP {response.status_code} after {attempts} attempts"
            )
        data = _parse_mcp_response_body(response.text)
        return data.get("result") or {}

    @staticmethod
    def _tool_result_from_payload(payload: Dict[str, Any]) -> ToolResult:
        if payload.get("isError"):
            content = payload.get("content") or []
            message = _extract_mcp_error_message(content) or "Tool call failed"
            return ToolResult.fail(message)

        structured = payload.get("structuredContent")
        if isinstance(structured, dict):
            return ToolResult.ok(structured)

        content = payload.get("content") or []
        text = _extract_mcp_text_content(content)
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
        config = instance_info.get("config") or {}
        config_collection_slug = config.get("collection_slug")
        instance_slug = instance_info.get("instance_slug")
        requested_collection_slug = merged_args.get("collection_slug")
        if config_collection_slug and (
            requested_collection_slug is None
            or requested_collection_slug == instance_slug
            or (
                isinstance(requested_collection_slug, str)
                and requested_collection_slug.startswith("collection-")
                and requested_collection_slug.removeprefix("collection-") == config_collection_slug
            )
        ):
            merged_args["collection_slug"] = config_collection_slug
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
        merged_args.setdefault("instance_context", {})
        if isinstance(merged_args["instance_context"], dict):
            merged_args["instance_context"].update(
                {
                    "data_instance_slug": target.data_instance_slug,
                    "provider_instance_slug": target.provider_instance_slug,
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
                elif credential_context.payload:
                    if self._mcp_credential_broker_required and not self._mcp_allow_raw_credential_fallback:
                        raise ValueError(
                            "MCP credential broker is required for this runtime; "
                            "raw credential fallback is disabled"
                        )
                    # Backward-compatible fallback for legacy MCP servers.
                    merged_args["instance_context"]["credentials"] = credential_context.payload

        data_instance_url = instance_info.get("data_instance_url") or _resolve_instance_url(data_config)
        if data_instance_url:
            for field_name in ("instance_url", "base_url", "url", "address"):
                merged_args.setdefault(field_name, data_instance_url)

        if credential_context and credential_context.payload:
            _apply_credential_hints(merged_args, credential_context)
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

    async def _mcp_initialize(self, provider_url: str, timeout_s: Optional[int]) -> str:
        now = time.monotonic()
        cached = self._mcp_sessions.get(provider_url)
        if cached and cached[1] > now:
            return cached[0]

        async with self._mcp_session_lock:
            cached = self._mcp_sessions.get(provider_url)
            if cached and cached[1] > time.monotonic():
                return cached[0]

            session_id = await self._mcp_initialize_fresh(provider_url, timeout_s)
            self._mcp_sessions[provider_url] = (session_id, time.monotonic() + self._mcp_session_ttl_s)
            return session_id

    async def _mcp_initialize_fresh(self, provider_url: str, timeout_s: Optional[int]) -> str:
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
            raise ValueError(f"MCP initialize failed with HTTP {response.status_code}")
        session_id = response.headers.get("mcp-session-id")
        if not session_id:
            raise ValueError("MCP initialize response missing mcp-session-id")
        return session_id

    async def _get_client(self, provider_url: str, timeout_s: int) -> httpx.AsyncClient:
        existing = self._clients.get(provider_url)
        if existing is not None:
            return existing

        async with self._client_lock:
            existing = self._clients.get(provider_url)
            if existing is not None:
                return existing
            client = httpx.AsyncClient(timeout=timeout_s)
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
    ) -> tuple[httpx.Response, int]:
        max_attempts = self._http_max_retries + 1
        last_response: Optional[httpx.Response] = None
        last_exception: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                response = await client.post(provider_url, headers=headers, json=payload)
                last_response = response
                if not self._is_retryable_status(response.status_code) or attempt == max_attempts:
                    return response, attempt
            except Exception as exc:
                last_exception = exc
                if not self._is_retryable_exception(exc) or attempt == max_attempts:
                    raise

            await asyncio.sleep(self._retry_delay_seconds(attempt))

        if last_response is not None:
            return last_response, max_attempts
        if last_exception is not None:
            raise last_exception
        raise RuntimeError("MCP request failed without response")

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


def _resolve_instance_url(config: Dict[str, Any]) -> Optional[str]:
    for field_name in ("url", "base_url", "instance_url", "address"):
        value = config.get(field_name)
        if isinstance(value, str) and value:
            return value
    return None


def _apply_credential_hints(
    merged_args: Dict[str, Any],
    credential_context: OperationCredentialContext,
) -> None:
    payload = credential_context.payload or {}
    merged_args.setdefault("credentials", payload)

    token = payload.get("token") or payload.get("api_key") or payload.get("access_token")
    if token:
        for field_name in ("token", "api_token", "api_key", "access_token"):
            merged_args.setdefault(field_name, token)

    username = payload.get("username")
    password = payload.get("password")
    if isinstance(username, str) and username:
        merged_args.setdefault("username", username)
    if isinstance(password, str) and password:
        merged_args.setdefault("password", password)
