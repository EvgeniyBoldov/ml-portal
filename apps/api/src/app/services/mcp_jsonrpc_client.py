from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx
from app.core.http.tls import outbound_http_verify
from portal_mcp_contract import MCPFailure, MCPFailureCategory, MCPFailureKind, is_sensitive_key, normalize_failure, public_user_message, safe_diagnostic


MCP_ACCEPT_HEADER = "application/json, text/event-stream"
MCP_PROTOCOL_VERSION = "2024-11-05"


class MCPCallFailure(ValueError):
    """Safe exception text with the normalized provider diagnosis attached."""

    def __init__(self, failure: Dict[str, Any]) -> None:
        self.mcp_failure = failure
        super().__init__(failure.get("user_message") or "The MCP source request failed.")


def _mcp_argument_secrets(value: Any, *, key: str = "") -> tuple[str, ...]:
    secrets: list[str] = []
    if isinstance(value, dict):
        for child_key, child in value.items():
            normalized_key = str(child_key).lower()
            if isinstance(child, str) and (is_sensitive_key(normalized_key) or normalized_key in {"dsn", "db_dsn"}):
                secrets.append(child)
            else:
                secrets.extend(_mcp_argument_secrets(child, key=normalized_key))
    elif isinstance(value, list):
        for child in value:
            secrets.extend(_mcp_argument_secrets(child, key=key))
    return tuple(item for item in secrets if item)


def _mcp_http_verify() -> bool | str:
    return outbound_http_verify()


def parse_mcp_response(body: str) -> Dict[str, Any]:
    payload = (body or "").strip()
    if not payload:
        raise ValueError("Empty MCP response body")
    try:
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise ValueError("MCP response root must be an object")
        return parsed
    except json.JSONDecodeError:
        pass

    data_lines = []
    for line in payload.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
    if data_lines:
        joined = "\n".join(data_lines).strip()
        if joined:
            parsed = json.loads(joined)
            if not isinstance(parsed, dict):
                raise ValueError("MCP response root must be an object")
            return parsed

    start = payload.find("{")
    if start >= 0:
        parsed = json.loads(payload[start:])
        if not isinstance(parsed, dict):
            raise ValueError("MCP response root must be an object")
        return parsed
    raise ValueError("Unable to parse MCP response body")


async def mcp_initialize(
    *,
    provider_url: str,
    timeout_s: int = 20,
) -> str:
    async with httpx.AsyncClient(timeout=timeout_s, verify=_mcp_http_verify()) as client:
        response = await client.post(
            provider_url,
            headers={
                "Content-Type": "application/json",
                "Accept": MCP_ACCEPT_HEADER,
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "ml-portal", "version": "1.0"},
                },
            },
        )
        response.raise_for_status()
        session_id = response.headers.get("mcp-session-id")
        if not session_id:
            raise ValueError("MCP initialize response missing mcp-session-id")
        return session_id


async def mcp_list_tools(
    *,
    provider_url: str,
    timeout_s: int = 30,
) -> list[Dict[str, Any]]:
    """Initialize an MCP session and return the full tools list."""
    async with httpx.AsyncClient(timeout=timeout_s, verify=_mcp_http_verify()) as client:
        init_response = await client.post(
            provider_url,
            headers={
                "Content-Type": "application/json",
                "Accept": MCP_ACCEPT_HEADER,
            },
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "ml-portal", "version": "1.0"},
                },
            },
        )
        init_response.raise_for_status()
        session_id = init_response.headers.get("mcp-session-id")
        if not session_id:
            raise ValueError(f"MCP initialize missing session id for {provider_url}")

        tools_response = await client.post(
            provider_url,
            headers={
                "Content-Type": "application/json",
                "Accept": MCP_ACCEPT_HEADER,
                "mcp-session-id": session_id,
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            },
        )
        tools_response.raise_for_status()
        payload = parse_mcp_response(tools_response.text)
        if isinstance(payload.get("error"), dict):
            code = payload["error"].get("code")
            suffix = f" (code {code})" if isinstance(code, int) else ""
            raise ValueError(f"MCP tools/list failed{suffix}")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("MCP tools/list response does not contain a result object")
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            raise ValueError("MCP tools/list response does not contain a tools array")
        return tools


async def mcp_call_tool(
    *,
    provider_url: str,
    session_id: str,
    tool_name: str,
    arguments: Optional[Dict[str, Any]] = None,
    timeout_s: int = 30,
) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout_s, verify=_mcp_http_verify()) as client:
        try:
            response = await client.post(
                provider_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": MCP_ACCEPT_HEADER,
                    "mcp-session-id": session_id,
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments or {},
                    },
                },
            )
        except httpx.HTTPError as exc:
            category = (
                MCPFailureCategory.AVAILABILITY
                if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))
                else MCPFailureCategory.UNKNOWN
            )
            raise MCPCallFailure(MCPFailure(
                kind=MCPFailureKind.TRANSPORT,
                category=category,
                code=type(exc).__name__,
                message=type(exc).__name__,
                details={"exception_type": type(exc).__name__},
                stage="tools_call",
                user_message=public_user_message(category),
            ).bounded_dump()) from exc
        if response.status_code >= 400:
            category = {
                401: MCPFailureCategory.AUTH,
                403: MCPFailureCategory.ACCESS,
                429: MCPFailureCategory.RATE_LIMIT,
                502: MCPFailureCategory.AVAILABILITY,
                503: MCPFailureCategory.AVAILABILITY,
                504: MCPFailureCategory.AVAILABILITY,
            }.get(response.status_code, MCPFailureCategory.UNKNOWN)
            secrets = _mcp_argument_secrets(arguments or {})
            try:
                source_details: Any = json.loads(response.content[:24000])
            except (ValueError, UnicodeDecodeError):
                source_details = response.text[:24000]
            failure = MCPFailure(
                kind=MCPFailureKind.HTTP,
                category=category,
                code=f"http_{response.status_code}",
                message=f"MCP request returned HTTP {response.status_code}",
                details=safe_diagnostic(source_details, secrets=secrets),
                stage="tools_call",
                http_status=response.status_code,
                user_message=public_user_message(category),
            ).bounded_dump()
            raise MCPCallFailure(failure)
        try:
            payload = parse_mcp_response(response.text)
        except Exception as exc:
            failure = MCPFailure(
                kind=MCPFailureKind.PROTOCOL,
                category=MCPFailureCategory.UNKNOWN,
                code=type(exc).__name__,
                message="MCP source returned an invalid response",
                details={"exception_type": type(exc).__name__},
                stage="tools_call",
                user_message=public_user_message(MCPFailureCategory.UNKNOWN),
            ).bounded_dump()
            raise MCPCallFailure(failure) from exc
        if payload.get("error"):
            error = payload["error"] if isinstance(payload["error"], dict) else {}
            secrets = _mcp_argument_secrets(arguments or {})
            failure = normalize_failure(error.get("data"), secrets=secrets)
            if failure is None:
                category = MCPFailureCategory.INPUT if error.get("code") == -32602 else MCPFailureCategory.UNKNOWN
                failure = MCPFailure(
                    kind=MCPFailureKind.RPC, category=category,
                    code=safe_diagnostic(error.get("code"), secrets=secrets) if error.get("code") is not None else None,
                    message=str(safe_diagnostic(error.get("message") or "MCP RPC error", secrets=secrets)),
                    details=safe_diagnostic(error.get("data"), secrets=secrets),
                    rpc_code=safe_diagnostic(error.get("code"), secrets=secrets), rpc_data=safe_diagnostic(error.get("data"), secrets=secrets),
                    user_message=public_user_message(category),
                ).bounded_dump()
            raise MCPCallFailure(failure)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise MCPCallFailure(MCPFailure(
                kind=MCPFailureKind.PROTOCOL,
                category=MCPFailureCategory.UNKNOWN,
                code="missing_result",
                message="MCP tools/call response has no result object",
                details=safe_diagnostic(payload, secrets=_mcp_argument_secrets(arguments or {})),
                stage="tools_call",
                user_message=public_user_message(MCPFailureCategory.UNKNOWN),
            ).bounded_dump())
        if result.get("isError"):
            meta = result.get("_meta") if isinstance(result.get("_meta"), dict) else {}
            failure = normalize_failure(meta.get("portal.failure"), secrets=_mcp_argument_secrets(arguments or {}))
            if failure is None:
                content = safe_diagnostic(result.get("content"), secrets=_mcp_argument_secrets(arguments or {}))
                message = "\n".join(
                    str(item.get("text")) for item in content
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                ) or "MCP tool reported an error"
                failure = MCPFailure(
                    kind=MCPFailureKind.TOOL,
                    category=MCPFailureCategory.UNKNOWN,
                    code="tool_error",
                    message=message,
                    details=safe_diagnostic(result, secrets=_mcp_argument_secrets(arguments or {})),
                    user_message=public_user_message(MCPFailureCategory.UNKNOWN),
                ).bounded_dump()
            result["content"] = safe_diagnostic(result.get("content"), secrets=_mcp_argument_secrets(arguments or {}))
            if "structuredContent" in result:
                result["structuredContent"] = safe_diagnostic(result["structuredContent"], secrets=_mcp_argument_secrets(arguments or {}))
            result["_meta"] = {**meta, "portal.failure": failure}
        return result


def mcp_result_error_message(result: Dict[str, Any]) -> Optional[str]:
    if not bool(result.get("isError")):
        return None
    meta = result.get("_meta") if isinstance(result.get("_meta"), dict) else {}
    failure = normalize_failure(meta.get("portal.failure"))
    if failure is not None:
        return failure["user_message"]
    # Legacy servers may return arbitrary upstream text in content. Keep this
    # health/user-facing helper safe; callers that need diagnostics consume the
    # normalized `portal.failure` envelope added by mcp_call_tool.
    return public_user_message(MCPFailureCategory.UNKNOWN)
