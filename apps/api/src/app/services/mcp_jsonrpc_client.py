from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx


MCP_ACCEPT_HEADER = "application/json, text/event-stream"
MCP_PROTOCOL_VERSION = "2024-11-05"


def parse_mcp_response(body: str) -> Dict[str, Any]:
    payload = (body or "").strip()
    if not payload:
        raise ValueError("Empty MCP response body")
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        pass

    data_lines = []
    for line in payload.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
    if data_lines:
        joined = "\n".join(data_lines).strip()
        if joined:
            return json.loads(joined)

    start = payload.find("{")
    if start >= 0:
        return json.loads(payload[start:])
    raise ValueError("Unable to parse MCP response body")


async def mcp_initialize(
    *,
    provider_url: str,
    timeout_s: int = 20,
) -> str:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
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
    async with httpx.AsyncClient(timeout=timeout_s) as client:
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
        tools = payload.get("result", {}).get("tools", [])
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
    async with httpx.AsyncClient(timeout=timeout_s) as client:
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
        response.raise_for_status()
        payload = parse_mcp_response(response.text)
        if payload.get("error"):
            message = str((payload.get("error") or {}).get("message") or "MCP rpc error")
            raise ValueError(message)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("Invalid MCP tools/call response: missing result object")
        return result


def mcp_result_error_message(result: Dict[str, Any]) -> Optional[str]:
    if not bool(result.get("isError")):
        return None
    content = result.get("content")
    if isinstance(content, list):
        texts = []
        for item in content:
            text = (item or {}).get("text") if isinstance(item, dict) else None
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
        if texts:
            return "\n".join(texts)
    return "MCP tool returned error"
