"""Portal HTTP MCP boundary: per-call broker credentials, tool policy, no secret sessions."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
import json
import logging
import time
from typing import Any
from urllib.parse import urlparse
import uuid

import httpx

from helpers.adapter_auth import AuthProfile, data_source_url, log_authentication_request, resolve_request_credential, upstream_auth_headers
from helpers.adapter_policy import INTERNAL_ARGUMENTS, ToolPolicy
from helpers.secret_broker import ResolvedCredential
from helpers.observability import (
    log_mcp_event,
    normalize_request_id,
    safe_error_detail,
    safe_target,
)
from portal_mcp_contract import (
    MCPFailure,
    MCPFailureCategory,
    MCPFailureKind,
    normalize_failure,
    public_user_message,
    safe_diagnostic,
)

logger = logging.getLogger("mcp.adapter")
PROTOCOL_VERSION = "2024-11-05"


class MCPAdapterFailure(RuntimeError):
    def __init__(self, failure: dict[str, Any]) -> None:
        self.failure = failure
        super().__init__(str(failure.get("user_message") or "MCP adapter request failed"))


@dataclass(frozen=True)
class AdapterConfig:
    upstream_url: str = "http://upstream/mcp"
    name: str = "portal-mcp-adapter"
    policy: ToolPolicy = field(default_factory=ToolPolicy)
    auth_profile: AuthProfile = field(default_factory=AuthProfile)
    timeout_s: float = 120
    broker_timeout_s: int = 10
    session_ttl_s: int = 3600
    max_request_bytes: int = 262144
    max_response_bytes: int = 1048576
    verify_ssl: bool | str = True
    allow_raw_credentials: bool = False
    # Discovery has no data-source credential. Some embedded upstreams require
    # a non-secret placeholder to initialize their schema-only tool surface.
    discovery_headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        parsed = urlparse(self.upstream_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Adapter requires an HTTP upstream URL without credentials")
        if min(self.timeout_s, self.broker_timeout_s, self.session_ttl_s, self.max_request_bytes, self.max_response_bytes) <= 0:
            raise ValueError("Adapter limits must be positive")


def _ok(rpc_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _error(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _credential_secret_values(credential: ResolvedCredential | None) -> tuple[str, ...]:
    if credential is None:
        return ()
    values: list[str] = []
    for key, value in credential.payload.items():
        if isinstance(value, str) and value and any(word in str(key).lower() for word in ("token", "password", "secret", "key")):
            values.append(value)
    return tuple(values)


def _tool_error_message(result: dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        parts = [item.get("text") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)]
        if parts:
            return "\n".join(parts)[:8000]
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and isinstance(structured.get("message"), str):
        return structured["message"][:8000]
    return "MCP tool reported an error"


def _failure_category(code: Any, message: Any, *, http_status: int | None = None) -> MCPFailureCategory:
    if http_status == 401:
        return MCPFailureCategory.AUTH
    if http_status == 403:
        return MCPFailureCategory.ACCESS
    if http_status == 429:
        return MCPFailureCategory.RATE_LIMIT
    if http_status in {502, 503, 504}:
        return MCPFailureCategory.AVAILABILITY
    if code == -32602:
        return MCPFailureCategory.INPUT
    return MCPFailureCategory.UNKNOWN


def _user_message(category: MCPFailureCategory) -> str:
    return public_user_message(category)


def _safe_rpc_log_code(code: Any) -> int | str:
    return code if isinstance(code, int) and not isinstance(code, bool) else "invalid_code"


def _safe_rpc_wire_code(code: Any) -> int:
    return code if isinstance(code, int) and not isinstance(code, bool) else -32000


def parse_response(body: bytes, rpc_id: Any) -> dict[str, Any]:
    """Select the matching JSON-RPC response, ignoring SSE notifications."""
    try:
        payload = json.loads(body)
    except ValueError:
        candidates: list[dict[str, Any]] = []
        lines: list[str] = []
        for line in body.decode().replace("\r\n", "\n").split("\n") + [""]:
            if line.startswith("data:"):
                lines.append(line[5:].lstrip())
            elif not line and lines:
                event = json.loads("\n".join(lines))
                if isinstance(event, dict):
                    candidates.append(event)
                lines = []
        payload = next((p for p in candidates if p.get("id") == rpc_id), None)
    if not isinstance(payload, dict) or payload.get("id") != rpc_id:
        raise ValueError("Invalid upstream MCP response")
    if "result" not in payload and "error" not in payload:
        raise ValueError("Upstream MCP response has neither result nor error")
    return payload


class MCPAdapter:
    def __init__(self, config: AdapterConfig, *, upstream_app: Any = None, transport: Any = None) -> None:
        self.config = config
        self.upstream_app = upstream_app
        self.transport = transport
        self.sessions: dict[str, float] = {}

    def _classify_failure(self, code: Any, message: Any, *, http_status: int | None = None) -> MCPFailureCategory:
        return _failure_category(code, message, http_status=http_status)

    def _source_failure_details(self) -> Any:
        return None

    def _source_failure_message(self, message: str, details: Any) -> str:
        return message

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            if self.upstream_app is not None:
                await self.upstream_app(scope, receive, send)
            else:
                while True:
                    message = await receive()
                    if message["type"] == "lifespan.startup":
                        await send({"type": "lifespan.startup.complete"})
                    elif message["type"] == "lifespan.shutdown":
                        await send({"type": "lifespan.shutdown.complete"})
                        return
            return
        if scope["type"] != "http":
            return
        if scope.get("path") == "/healthz":
            await self._respond(send, 200, {"status": "ok"})
            return
        if scope.get("path") not in {"/", "/mcp"}:
            await self._respond(send, 404, {"detail": "Not found"})
            return
        if scope.get("method") != "POST":
            await self._respond(send, 405, {"detail": "Use HTTP POST"})
            return
        started = time.monotonic()
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        request_id = normalize_request_id(headers.get("x-portal-request-id"))
        rpc_id: Any = None
        method, tool, stage = "unknown", "", "request_parse"
        credential = None
        forward_headers: dict[str, str] = {}
        data_instance_id = ""
        provider_instance_id = ""
        target_url = self.config.upstream_url
        secret_values: tuple[str, ...] = ()
        try:
            async with asyncio.timeout(self.config.timeout_s):
                body = bytearray()
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    body.extend(message.get("body", b""))
                    if len(body) > self.config.max_request_bytes:
                        raise ValueError("Adapter request size limit exceeded")
                    if not message.get("more_body"):
                        break
                request = json.loads(body)
                if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                    raise ValueError("Invalid JSON-RPC request")
                rpc_id, method = request.get("id"), str(request.get("method") or "")
                log_mcp_event(
                    logger,
                    outcome="started",
                    request_id=request_id,
                    server=self.config.name,
                    method=method,
                    stage="request_received",
                    target=safe_target(self.config.upstream_url),
                )
                params = request.get("params") or {}
                if not isinstance(params, dict):
                    raise ValueError("Invalid JSON-RPC params")
                if method == "initialize":
                    now = time.monotonic()
                    self.sessions = {s: exp for s, exp in self.sessions.items() if exp > now}
                    session = str(uuid.uuid4())
                    self.sessions[session] = now + self.config.session_ttl_s
                    log_mcp_event(
                        logger,
                        outcome="completed",
                        request_id=request_id,
                        server=self.config.name,
                        method=method,
                        stage="session_initialized",
                        target=safe_target(self.config.upstream_url),
                        http_status=200,
                    )
                    await self._respond(send, 200, _ok(rpc_id, {
                        "protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": self.config.name, "version": "1.0.0"},
                    }), {"mcp-session-id": session})
                    return
                stage = "session_validation"
                session = headers.get("mcp-session-id", "")
                if self.sessions.get(session, 0) <= time.monotonic():
                    self.sessions.pop(session, None)
                    log_mcp_event(
                        logger,
                        outcome="failed",
                        request_id=request_id,
                        server=self.config.name,
                        method=method,
                        stage="session_validation",
                        target=safe_target(self.config.upstream_url),
                        error_type="SessionNotInitialized",
                        rpc_code=-32002,
                    )
                    await self._respond(send, 200, _error(rpc_id, -32002, "Session not initialized"))
                    return
                self.sessions[session] = time.monotonic() + self.config.session_ttl_s
                if method == "notifications/initialized":
                    await self._respond(send, 202, None)
                    return
                if method == "ping":
                    await self._respond(send, 200, _ok(rpc_id, {}))
                    return
                if method not in {"tools/list", "tools/call"}:
                    await self._respond(send, 200, _error(rpc_id, -32601, "Method not found"))
                    return
                forward_headers = dict(self.config.discovery_headers)
                if method == "tools/call":
                    tool = str(params.get("name") or "")
                    stage = "tool_allowlist"
                    if not self.config.policy.allows(tool):
                        log_mcp_event(
                            logger,
                            outcome="failed",
                            request_id=request_id,
                            server=self.config.name,
                            method=method,
                            tool=tool,
                            stage=stage,
                            error_type="ToolNotAllowed",
                            rpc_code=-32601,
                        )
                        await self._respond(send, 200, _error(rpc_id, -32601, "Unknown tool"))
                        return
                    try:
                        self.config.policy.risk_level(tool)
                    except ValueError:
                        log_mcp_event(
                            logger,
                            outcome="failed",
                            request_id=request_id,
                            server=self.config.name,
                            method=method,
                            tool=tool,
                            stage="tool_risk_policy",
                            error_type="RiskClassificationMissing",
                            rpc_code=-32603,
                        )
                        await self._respond(
                            send,
                            200,
                            _error(rpc_id, -32603, "Tool risk classification is not configured"),
                        )
                        return
                    args = params.get("arguments") or {}
                    if not isinstance(args, dict):
                        raise ValueError("Invalid tool arguments")
                    context = args.get("instance_context")
                    context = context if isinstance(context, dict) else {}
                    data_instance_id = str(context.get("data_instance_id") or "")
                    provider_instance_id = str(context.get("provider_instance_id") or "")
                    credential_access = args.get("credential_access")
                    if not isinstance(credential_access, dict):
                        credential_access = context.get("credential_access") or {}
                    secret_values = ((str(credential_access.get("token")),)
                                     if isinstance(credential_access, dict) and credential_access.get("token") else ())
                    stage = "credential_resolution"
                    credential = await self._resolve_credential(args, request_id, tool)
                    secret_values = (*_credential_secret_values(credential), *secret_values)
                    target_url = self._source_url(args, credential, tool)
                    stage = "upstream_authentication"
                    forward_headers = upstream_auth_headers(
                        credential, profile=self.config.auth_profile, tool_name=tool,
                        target_url=target_url,
                    )
                    log_authentication_request(
                        credential, profile=self.config.auth_profile, headers=forward_headers,
                        request_id=request_id, tool_name=tool, target_url=target_url,
                    )
                    log_mcp_event(
                        logger,
                        outcome="completed",
                        request_id=request_id,
                        server=self.config.name,
                        method=method,
                        tool=tool,
                        stage="upstream_authentication",
                        target=safe_target(target_url or self.config.upstream_url),
                        data_instance_id=data_instance_id,
                        provider_instance_id=provider_instance_id,
                        credential_id=credential.credential_id,
                        auth_type=credential.auth_type,
                        auth_headers=",".join(sorted(forward_headers)),
                    )
                    request = {**request, "params": {**params, "arguments": {
                        key: value for key, value in args.items() if key not in INTERNAL_ARGUMENTS
                    }}}
                stage = "upstream_request"
                async with self._upstream_context(credential, tool):
                    payload = await self._forward(request, forward_headers, request_id, secrets=secret_values)
                if method == "tools/list":
                    stage = "tool_descriptors"
                    payload = self.config.policy.filter_result(payload)
                failed = bool(payload.get("error") or (payload.get("result") or {}).get("isError"))
                upstream_error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
                log_mcp_event(
                    logger, outcome="failed" if failed else "completed", request_id=request_id,
                    server=self.config.name, method=method, tool=tool, stage=stage,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    target=safe_target(target_url or self.config.upstream_url),
                    data_instance_id=data_instance_id,
                    provider_instance_id=provider_instance_id,
                    credential_id=credential.credential_id if credential else "",
                    auth_type=credential.auth_type if credential else "",
                    rpc_code=_safe_rpc_log_code(upstream_error.get("code")),
                    rpc_message="upstream_error" if upstream_error else ("tool_isError" if failed else ""),
                )
                if isinstance(payload.get("error"), dict):
                    upstream = payload["error"]
                    diagnostic = normalize_failure(upstream.get("data"), secrets=secret_values)
                    if diagnostic is not None:
                        diagnostic = MCPFailure.model_validate({
                            **diagnostic,
                            "request_id": diagnostic.get("request_id") or request_id,
                            "stage": diagnostic.get("stage") or stage,
                        }).bounded_dump()
                    else:
                        diagnostic = MCPFailure(
                            kind=MCPFailureKind.RPC,
                            category=self._classify_failure(upstream.get("code"), upstream.get("message")),
                            code=safe_diagnostic(upstream.get("code"), secrets=secret_values) if upstream.get("code") is not None else None,
                            message=str(safe_diagnostic(upstream.get("message") or "MCP RPC error", secrets=secret_values)),
                            details=safe_diagnostic(upstream.get("data"), secrets=secret_values),
                            request_id=request_id,
                            stage=stage,
                            rpc_code=safe_diagnostic(upstream.get("code"), secrets=secret_values),
                            rpc_data=safe_diagnostic(upstream.get("data"), secrets=secret_values),
                            user_message=_user_message(self._classify_failure(upstream.get("code"), upstream.get("message"))),
                        ).bounded_dump()
                    # Keep MCP's public error concise; preserve source diagnostics
                    # in the typed error.data contract for capable callers.
                    payload["error"] = {
                        "code": _safe_rpc_wire_code(upstream.get("code")),
                        "message": "MCP upstream request failed",
                        "data": diagnostic,
                    }
                elif isinstance(payload.get("result"), dict) and payload["result"].get("isError"):
                    result = safe_diagnostic(payload["result"], secrets=secret_values)
                    message = _tool_error_message(result)
                    source_failures = self._source_failure_details()
                    if source_failures:
                        message = self._source_failure_message(message, source_failures)
                        details = {"tool_result": result, "source_failures": safe_diagnostic(source_failures, secrets=secret_values)}
                    else:
                        details = result
                    meta = result.get("_meta") if isinstance(result.get("_meta"), dict) else {}
                    diagnostic = normalize_failure(meta.get("portal.failure"), secrets=secret_values)
                    if diagnostic is not None:
                        preserved_details = diagnostic.get("details")
                        if source_failures:
                            if isinstance(preserved_details, dict):
                                preserved_details = {
                                    **preserved_details,
                                    "source_failures": safe_diagnostic(source_failures, secrets=secret_values),
                                }
                            else:
                                preserved_details = {
                                    "upstream_details": preserved_details,
                                    "source_failures": safe_diagnostic(source_failures, secrets=secret_values),
                                }
                        diagnostic = MCPFailure.model_validate({
                            **diagnostic,
                            "request_id": diagnostic.get("request_id") or request_id,
                            "stage": diagnostic.get("stage") or stage,
                            "details": preserved_details if preserved_details is not None else details,
                        }).bounded_dump()
                    else:
                        diagnostic = MCPFailure(
                            kind=MCPFailureKind.TOOL,
                            category=self._classify_failure(None, message),
                            code="tool_error",
                            message=str(safe_diagnostic(message, secrets=secret_values)),
                            details=details,
                            request_id=request_id,
                            stage=stage,
                            user_message=_user_message(self._classify_failure(None, message)),
                        ).bounded_dump()
                    result["_meta"] = {**meta, "portal.failure": diagnostic}
                    payload["result"] = result
                await self._respond(send, 200, payload)
        except Exception as exc:
            sensitive_stage = stage in {"credential_resolution", "upstream_authentication"}
            log_mcp_event(
                logger, outcome="failed", request_id=request_id, server=self.config.name,
                method=method, tool=tool, stage=stage, error_type=type(exc).__name__,
                duration_ms=int((time.monotonic() - started) * 1000),
                http_status=getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None),
                rpc_code=-32000,
                target=safe_target(target_url or self.config.upstream_url),
                data_instance_id=data_instance_id,
                provider_instance_id=provider_instance_id,
                credential_id=credential.credential_id if credential else "",
                auth_type=credential.auth_type if credential else "",
                auth_headers=",".join(sorted(forward_headers)),
                error_detail="-" if sensitive_stage else str(safe_diagnostic(safe_error_detail(exc), secrets=secret_values)),
            )
            # Keep a useful typed transport diagnosis without returning arbitrary
            # exception text, request/response bodies, or credential values.
            http_status = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
            kind = (MCPFailureKind.HTTP if http_status else
                    MCPFailureKind.PROTOCOL if isinstance(exc, ValueError) else MCPFailureKind.TRANSPORT)
            category = self._classify_failure(None, "", http_status=http_status)
            if kind == MCPFailureKind.TRANSPORT and isinstance(exc, (TimeoutError, httpx.TimeoutException, httpx.ConnectError)):
                category = MCPFailureCategory.AVAILABILITY
            diagnostic = exc.failure if isinstance(exc, MCPAdapterFailure) else MCPFailure(
                kind=kind,
                category=category,
                code=type(exc).__name__,
                message=("Credential resolution failed" if sensitive_stage else
                         str(safe_diagnostic(safe_error_detail(exc) or type(exc).__name__, secrets=secret_values))),
                details={"exception_type": type(exc).__name__} if sensitive_stage else {
                    "exception_type": type(exc).__name__,
                    "detail": str(safe_diagnostic(safe_error_detail(exc), secrets=secret_values)),
                },
                request_id=request_id,
                stage=stage,
                http_status=http_status,
                user_message=_user_message(category),
            ).bounded_dump()
            response = _error(rpc_id, -32000, "MCP adapter request failed")
            response["error"]["data"] = diagnostic
            await self._respond(send, 200, response)

    async def _resolve_credential(
        self, arguments: dict[str, Any], request_id: str, tool: str,
    ) -> ResolvedCredential:
        return await resolve_request_credential(
            arguments, timeout_s=self.config.broker_timeout_s,
            allow_raw=self.config.allow_raw_credentials, request_id=request_id,
            server=self.config.name, tool=tool,
        )

    def _source_url(self, arguments: dict[str, Any], credential: ResolvedCredential, tool: str) -> str:
        return data_source_url(arguments, credential.payload, tool_name=tool)

    @asynccontextmanager
    async def _upstream_context(
        self, credential: ResolvedCredential | None, tool: str,
    ) -> AsyncIterator[None]:
        yield

    async def _forward(self, request: dict[str, Any], auth: dict[str, str], request_id: str,
                       *, secrets: tuple[str, ...] = ()) -> dict[str, Any]:
        transport = self.transport
        if self.upstream_app is not None:
            transport = httpx.ASGITransport(app=self.upstream_app)
        async with httpx.AsyncClient(
            transport=transport, timeout=self.config.timeout_s, verify=self.config.verify_ssl,
            follow_redirects=False, trust_env=False,
        ) as client:
            headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", **auth,
                       "x-portal-request-id": request_id}
            init_id = str(uuid.uuid4())
            logger.info(
                "mcp_upstream_stage_started request_id=%s server=%s stage=initialize target=%s",
                request_id,
                self.config.name,
                safe_target(self.config.upstream_url),
            )
            initialized, init_headers = await self._post(client, headers, {
                "jsonrpc": "2.0", "id": init_id, "method": "initialize",
                "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                           "clientInfo": {"name": self.config.name, "version": "1.0.0"}},
            }, request_id=request_id, stage="initialize", secrets=secrets)
            if initialized.get("error"):
                logger.warning(
                    "mcp_upstream_stage_failed request_id=%s server=%s stage=initialize rpc_code=%s",
                    request_id,
                    self.config.name,
                    _safe_rpc_log_code((initialized.get("error") or {}).get("code")) if isinstance(initialized.get("error"), dict) else "-",
                )
                rpc = initialized["error"]
                failure = MCPFailure(
                    kind=MCPFailureKind.RPC,
                    category=self._classify_failure(rpc.get("code"), rpc.get("message")),
                    code=safe_diagnostic(rpc.get("code"), secrets=secrets) if rpc.get("code") is not None else None,
                    message=str(safe_diagnostic(rpc.get("message") or "MCP initialization failed", secrets=secrets)),
                    details=safe_diagnostic(rpc.get("data"), secrets=secrets),
                    request_id=request_id, stage="initialize", rpc_code=safe_diagnostic(rpc.get("code"), secrets=secrets),
                    rpc_data=safe_diagnostic(rpc.get("data"), secrets=secrets),
                    user_message="The MCP source could not be initialized.",
                ).bounded_dump()
                raise MCPAdapterFailure(failure)
            logger.info(
                "mcp_upstream_stage_completed request_id=%s server=%s stage=initialize http_status=200 session_received=%s",
                request_id,
                self.config.name,
                bool(init_headers.get("mcp-session-id")),
            )
            if init_headers.get("mcp-session-id"):
                headers["mcp-session-id"] = init_headers["mcp-session-id"]
            negotiated = (initialized.get("result") or {}).get("protocolVersion")
            if negotiated:
                headers["MCP-Protocol-Version"] = str(negotiated)
            logger.info(
                "mcp_upstream_stage_started request_id=%s server=%s stage=notifications_initialized target=%s",
                request_id,
                self.config.name,
                safe_target(self.config.upstream_url),
            )
            await self._post(
                client,
                headers,
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                request_id=request_id,
                stage="notifications_initialized",
                secrets=secrets,
            )
            logger.info(
                "mcp_upstream_stage_completed request_id=%s server=%s stage=notifications_initialized",
                request_id,
                self.config.name,
            )
            # A tools/call is sent exactly once. Session credentials are never
            # cached, shared, or used to retry a possibly executed operation.
            logger.info(
                "mcp_upstream_stage_started request_id=%s server=%s stage=%s tool=%s target=%s",
                request_id,
                self.config.name,
                request.get("method"),
                ((request.get("params") or {}).get("name") or "-"),
                safe_target(self.config.upstream_url),
            )
            response, response_headers = await self._post(
                client,
                headers,
                request,
                request_id=request_id,
                stage="tools_call" if request.get("method") == "tools/call" else str(request.get("method")),
                tool=str(((request.get("params") or {}).get("name") or "")),
                secrets=secrets,
            )
            error = response.get("error") if isinstance(response.get("error"), dict) else {}
            logger.info(
                "mcp_upstream_stage_%s request_id=%s server=%s stage=tools_call tool=%s rpc_code=%s response_content_type=%s",
                "failed" if error else "completed",
                request_id,
                self.config.name,
                ((request.get("params") or {}).get("name") or "-"),
                    _safe_rpc_log_code(error.get("code")) if error else "-",
                response_headers.get("content-type", "-"),
            )
            return response

    async def _post(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        payload: dict[str, Any],
        *,
        request_id: str = "",
        stage: str = "upstream_request",
        tool: str = "",
        secrets: tuple[str, ...] = (),
    ) -> tuple[dict[str, Any], httpx.Headers]:
        try:
            async with client.stream("POST", self.config.upstream_url, headers=headers, json=payload) as response:
                body = bytearray()
                truncated = False
                async for chunk in response.aiter_bytes():
                    remaining = self.config.max_response_bytes - len(body)
                    body.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        truncated = True
                        break
                    if response.status_code < 400 and len(body) > self.config.max_response_bytes:
                        raise ValueError("Adapter response size limit exceeded")
                if response.status_code >= 400:
                    log_mcp_event(
                        logger, outcome="failed", request_id=request_id, server=self.config.name,
                        method=str(payload.get("method") or "notification"), tool=tool, stage=stage,
                        target=safe_target(self.config.upstream_url), http_status=response.status_code,
                        error_type="UpstreamHTTPError",
                    )
                    try:
                        detail: Any = json.loads(body) if body else None
                    except (ValueError, UnicodeDecodeError):
                        detail = body.decode("utf-8", errors="replace")
                    if truncated:
                        detail = {"body": detail, "_truncated": True}
                    category = self._classify_failure(None, "", http_status=response.status_code)
                    raise MCPAdapterFailure(MCPFailure(
                        kind=MCPFailureKind.HTTP, category=category,
                        code=f"http_{response.status_code}",
                        message=f"Upstream returned HTTP {response.status_code}",
                        details=safe_diagnostic(detail, secrets=secrets), request_id=request_id,
                        stage=stage, http_status=response.status_code,
                        user_message=_user_message(category),
                    ).bounded_dump())
                if truncated:
                    raise ValueError("Adapter response size limit exceeded")
                log_mcp_event(
                    logger, outcome="completed", request_id=request_id, server=self.config.name,
                    method=str(payload.get("method") or "notification"), tool=tool, stage=stage,
                    target=safe_target(self.config.upstream_url), http_status=response.status_code,
                    response_bytes=len(body),
                )
                if "id" not in payload:
                    return {}, response.headers
                try:
                    parsed = parse_response(bytes(body), payload["id"])
                except Exception as exc:
                    raise MCPAdapterFailure(MCPFailure(
                        kind=MCPFailureKind.PROTOCOL, category=MCPFailureCategory.UNKNOWN,
                        code=type(exc).__name__, message=str(safe_diagnostic(str(exc), secrets=secrets)),
                        details={"response_bytes": len(body)}, request_id=request_id, stage=stage,
                        user_message="The MCP source returned an invalid response.",
                    ).bounded_dump()) from exc
                return parsed, response.headers
        except MCPAdapterFailure:
            raise
        except httpx.HTTPError as exc:
            detail = safe_error_detail(exc)
            raise MCPAdapterFailure(MCPFailure(
                kind=MCPFailureKind.TRANSPORT, category=MCPFailureCategory.AVAILABILITY,
                code=type(exc).__name__, message=str(safe_diagnostic(detail or type(exc).__name__, secrets=secrets)),
                details={"exception_type": type(exc).__name__}, request_id=request_id, stage=stage,
                user_message="The MCP source could not be reached.",
            ).bounded_dump()) from exc

    @staticmethod
    async def _respond(send: Any, status: int, payload: Any, headers: dict[str, str] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else b""
        response_headers = {"content-type": "application/json", **(headers or {})}
        await send({"type": "http.response.start", "status": status,
                    "headers": [(k.encode(), v.encode()) for k, v in response_headers.items()]})
        await send({"type": "http.response.body", "body": body})
