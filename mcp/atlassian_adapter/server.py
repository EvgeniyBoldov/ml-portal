from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from typing import Any

from helpers.secret_broker import SecretBrokerClient, extract_credential_access

logger = logging.getLogger("mcp.atlassian.adapter")
BROKER_TIMEOUT_SECONDS = int(os.environ.get("MCP_SECRET_BROKER_TIMEOUT_SECONDS", "10"))
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("ATLASSIAN_MCP_TIMEOUT_SECONDS", "120"))
JIRA_URL = os.environ.get("JIRA_URL", "").strip()
CONFLUENCE_URL = os.environ.get("CONFLUENCE_URL", "").strip()
DEFAULT_TOOLS = "jira_search,jira_get_issue,jira_get_project_issues,confluence_search,confluence_get_page"
_configured_tools = os.environ.get("ATLASSIAN_MCP_ENABLED_TOOLS", "").strip() or DEFAULT_TOOLS
ENABLED_TOOLS = {
    name.strip()
    for name in _configured_tools.split(",")
    if name.strip()
}
SESSIONS: dict[str, float] = {}
SESSION_TTL_SECONDS = 3600
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "ml-portal-atlassian-mcp-adapter", "version": "1.0.0"}
_DESTRUCTIVE = re.compile(r"(^|_)(delete|remove|destroy|purge|revoke|archive|deactivate|drop)(_|$)", re.I)
_INTERNAL_ARGUMENTS = {
    "credential_access", "instance_context", "base_url", "url", "address", "instance_url",
    "provider_url", "data_instance_url", "jira_url", "confluence_url",
}


def _risk(tool: dict[str, Any]) -> dict[str, Any]:
    schema = dict(tool.get("inputSchema") or {})
    runtime_metadata = schema.get("x-runtime")
    metadata = dict(runtime_metadata) if isinstance(runtime_metadata, dict) else {}
    annotations = tool.get("annotations") or {}
    if not metadata.get("risk_level"):
        name = str(tool.get("name") or "")
        if annotations.get("readOnlyHint") is True:
            risk = "safe"
        elif annotations.get("destructiveHint") is True or _DESTRUCTIVE.search(name):
            risk = "destructive"
        elif annotations.get("readOnlyHint") is False:
            risk = "write"
        else:
            risk = "destructive"
        metadata["risk_level"] = risk
    risk = metadata["risk_level"]
    effective_risk = risk if risk in {"safe", "write", "destructive"} else "destructive"
    metadata.setdefault("side_effects", effective_risk != "safe")
    metadata.setdefault("requires_confirmation", effective_risk != "safe")
    metadata.setdefault("credential_scope", "user")
    schema["x-runtime"] = metadata
    tool["inputSchema"] = schema
    return tool


def _error(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _ok(rpc_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


async def _resolve_auth(params: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    args = params.get("arguments") or {}
    access = extract_credential_access(args)
    if not access:
        raise ValueError("Atlassian MCP requires broker credential_access")
    credential = await SecretBrokerClient(timeout_s=BROKER_TIMEOUT_SECONDS).resolve(access)
    payload = credential.payload
    headers: dict[str, str] = {}
    tool_name = str(params.get("name") or "")
    product = "Confluence" if tool_name.startswith("confluence_") else "Jira"
    token_keys = (
        ("confluence_personal_token", "personal_token", "personal_access_token", "pat", "token")
        if product == "Confluence"
        else ("jira_personal_token", "personal_token", "personal_access_token", "pat", "token")
    )
    token = next((str(payload.get(key) or "").strip() for key in token_keys if payload.get(key)), "")
    context = args.get("instance_context") if isinstance(args.get("instance_context"), dict) else {}
    context_config = context.get("config") if isinstance(context.get("config"), dict) else {}
    product_key = "confluence_url" if product == "Confluence" else "jira_url"
    product_url = next((str(source.get(product_key) or "").strip() for source in (payload, context_config, context) if source.get(product_key)), "")
    if not product_url:
        product_url = next((str(payload.get(key) or "").strip() for key in ("base_url", "url") if payload.get(key)), "")
    if not product_url:
        product_url = next((str(source.get(key) or "").strip() for source in (context, context_config) for key in ("data_instance_url", "instance_url") if source.get(key)), "")
    if not product_url:
        product_url = CONFLUENCE_URL if product == "Confluence" else JIRA_URL
    auth_type = str(credential.auth_type or "").strip().lower()
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or payload.get("api_token") or "").strip()
    access_token = str(payload.get("access_token") or "").strip()
    if auth_type in {"oauth", "bearer"} or (access_token and not token):
        bearer = access_token or token
        if not bearer:
            raise ValueError("Resolved OAuth credential has no access token")
        headers["Authorization"] = f"Bearer {bearer}"
    elif username and password and (auth_type in {"basic", "api_token"} or not token):
        import base64
        headers["Authorization"] = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
    elif token:
        if product_url:
            headers[f"X-Atlassian-{product}-Url"] = product_url
            headers[f"X-Atlassian-{product}-Personal-Token"] = token
        else:
            headers["Authorization"] = f"Token {token}"
    else:
        raise ValueError("Resolved credential payload has no supported Atlassian credentials")
    if product_url:
        headers[f"X-Atlassian-{product}-Url"] = product_url
    headers["Accept"] = "application/json, text/event-stream"
    return headers, args


async def _handle(scope: dict[str, Any], body: bytes, send: Any, upstream: Any) -> None:
    try:
        request = json.loads(body or b"{}")
        rpc_id, method, params = request.get("id"), request.get("method"), request.get("params") or {}
        incoming_headers = {key.decode().lower(): value.decode() for key, value in scope.get("headers", [])}
        response_headers: list[tuple[bytes, bytes]] = [(b"content-type", b"application/json")]
        if method == "initialize":
            now = time.monotonic()
            for expired in [key for key, expiry in SESSIONS.items() if expiry <= now]:
                SESSIONS.pop(expired, None)
            session_id = str(uuid.uuid4())
            SESSIONS[session_id] = now + SESSION_TTL_SECONDS
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            }
            response_headers.append((b"mcp-session-id", session_id.encode()))
            await _respond(send, 200, response_headers, _ok(rpc_id, result))
            return
        session_id = incoming_headers.get("mcp-session-id")
        now = time.monotonic()
        if session_id and SESSIONS.get(session_id, 0) <= now:
            SESSIONS.pop(session_id, None)
        if not session_id or SESSIONS.get(session_id, 0) <= now:
            await _respond(send, 200, response_headers, _error(rpc_id, -32002, "Session not initialized"))
            return
        if method == "notifications/initialized":
            await _respond_empty(send, 202)
            return
        if method == "ping":
            await _respond(send, 200, response_headers, _ok(rpc_id, {}))
            return
        forward_headers = {"content-type": "application/json", "accept": "application/json, text/event-stream"}
        if method == "tools/call":
            tool_name = str(params.get("name") or "")
            if ENABLED_TOOLS and tool_name not in ENABLED_TOOLS:
                await _respond(send, 200, response_headers, _error(rpc_id, -32601, "Unknown tool"))
                return
            auth_headers, args = await _resolve_auth(params)
            forward_headers.update(auth_headers)
            public_args = {key: value for key, value in args.items() if key not in _INTERNAL_ARGUMENTS}
            request["params"]["arguments"] = public_args
        elif method != "tools/list":
            await _respond(send, 200, response_headers, _error(rpc_id, -32601, "Method not found"))
            return
        # Upstream stateless Streamable HTTP still requires an MCP initialize
        # exchange before each standalone JSON-RPC request. The placeholder
        # identity is used only to expose schemas; actual tool calls carry the
        # per-call broker credential resolved above.
        listing_headers = {
            "content-type": "application/json",
            "accept": "application/json, text/event-stream",
            "authorization": "Token broker-managed-placeholder",
        }
        initialized = await upstream.post(
            "/mcp",
            headers=listing_headers,
            json={
                "jsonrpc": "2.0", "id": f"adapter-init-{uuid.uuid4()}",
                "method": "initialize",
                "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}, "clientInfo": SERVER_INFO},
            },
        )
        initialized.raise_for_status()
        response = await upstream.post("/mcp", headers=forward_headers if method == "tools/call" else listing_headers, json=request)
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError:
            data_lines = [line[5:].strip() for line in response.text.splitlines() if line.startswith("data:")]
            if not data_lines:
                raise ValueError("Upstream MCP response is not JSON or an MCP event stream")
            payload = json.loads("\n".join(data_lines))
        if method == "tools/list" and isinstance(payload.get("result", {}).get("tools"), list):
            tools = payload["result"]["tools"]
            tools = [tool for tool in tools if not ENABLED_TOOLS or tool.get("name") in ENABLED_TOOLS]
            payload["result"]["tools"] = [_risk(tool) for tool in tools]
        await _respond(send, response.status_code, response_headers, payload)
    except Exception as exc:  # Do not expose upstream error text, which may contain credentials.
        logger.warning("atlassian_adapter_request_failed error_type=%s", type(exc).__name__)
        await _respond(send, 200, [(b"content-type", b"application/json")], _error(request.get("id") if "request" in locals() else None, -32000, "Atlassian MCP request failed"))


async def _respond(send: Any, status: int, headers: list[tuple[bytes, bytes]], payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode()
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


async def _respond_empty(send: Any, status: int) -> None:
    await send({"type": "http.response.start", "status": status, "headers": []})
    await send({"type": "http.response.body", "body": b""})


class Adapter:
    """HTTP MCP gateway that adds broker credentials, risk metadata and tool filtering."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == "/healthz":
            await _respond(send, 200, [(b"content-type", b"application/json")], {"status": "ok"})
            return
        if scope.get("path") not in {"/", "/mcp"}:
            await _respond(send, 404, [(b"content-type", b"application/json")], {"detail": "Not found"})
            return
        message = await receive()
        body = message.get("body", b"")
        while message.get("more_body"):
            message = await receive()
            body += message.get("body", b"")
        from httpx import ASGITransport, AsyncClient
        async with AsyncClient(transport=ASGITransport(app=self.app), base_url="http://upstream", timeout=REQUEST_TIMEOUT_SECONDS) as upstream:
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                    await _handle(scope, body, send, upstream)
            except TimeoutError:
                try:
                    rpc_id = json.loads(body or b"{}").get("id")
                except (ValueError, AttributeError):
                    rpc_id = None
                await _respond(send, 200, [(b"content-type", b"application/json")], _error(rpc_id, -32000, "Atlassian MCP request timed out"))


def _build_app() -> Any:
    # The official package exposes its FastMCP instance. Stateless mode lets the
    # adapter own portal sessions while passing a fresh PAT on each tool call.
    from mcp_atlassian.servers.main import main_mcp
    upstream_app = main_mcp.http_app(path="/mcp", stateless_http=True, transport="streamable-http")
    return Adapter(upstream_app)


app = _build_app()
