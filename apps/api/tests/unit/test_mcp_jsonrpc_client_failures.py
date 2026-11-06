from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app.services.mcp_jsonrpc_client import MCPCallFailure, mcp_call_tool, mcp_result_error_message


class _Client:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def post(self, *_args, **_kwargs):
        if self.error is not None:
            raise self.error
        return self.response


def _response(payload, status=200):
    body = json.dumps(payload)
    return SimpleNamespace(status_code=status, content=body.encode(), text=body)


@pytest.mark.asyncio
async def test_mcp_client_transport_failure_is_normalized_with_stage():
    with patch("app.services.mcp_jsonrpc_client.httpx.AsyncClient", return_value=_Client(error=httpx.ConnectError("offline"))):
        with pytest.raises(MCPCallFailure) as raised:
            await mcp_call_tool(provider_url="https://mcp.example", session_id="s", tool_name="search")
    failure = raised.value.mcp_failure
    assert failure["kind"] == "transport"
    assert failure["category"] == "availability"
    assert failure["stage"] == "tools_call"


@pytest.mark.asyncio
async def test_mcp_client_jsonrpc_error_preserves_code_and_data():
    response = _response({"jsonrpc": "2.0", "id": 2, "error": {
        "code": -32017, "message": "query parser failed", "data": {"cause": "invalid CQL"},
    }})
    with patch("app.services.mcp_jsonrpc_client.httpx.AsyncClient", return_value=_Client(response=response)):
        with pytest.raises(MCPCallFailure) as raised:
            await mcp_call_tool(provider_url="https://mcp.example", session_id="s", tool_name="search")
    failure = raised.value.mcp_failure
    assert failure["kind"] == "rpc"
    assert failure["rpc_code"] == -32017
    assert failure["rpc_data"] == {"cause": "invalid CQL"}
    assert failure["message"] == "query parser failed"


@pytest.mark.asyncio
async def test_mcp_client_legacy_iserror_is_normalized_and_public_message_is_safe():
    response = _response({"jsonrpc": "2.0", "id": 2, "result": {
        "isError": True, "content": [{"type": "text", "text": "upstream CQL parse failure"}],
        "structuredContent": {"reason": "invalid CQL"},
    }})
    with patch("app.services.mcp_jsonrpc_client.httpx.AsyncClient", return_value=_Client(response=response)):
        result = await mcp_call_tool(provider_url="https://mcp.example", session_id="s", tool_name="search")
    failure = result["_meta"]["portal.failure"]
    assert failure["kind"] == "tool"
    assert failure["message"] == "upstream CQL parse failure"
    assert failure["details"]["structuredContent"]["reason"] == "invalid CQL"
    assert mcp_result_error_message(result) == "The source request failed."


@pytest.mark.asyncio
async def test_mcp_client_non_object_json_response_is_protocol_failure():
    response = SimpleNamespace(status_code=200, content=b"[]", text="[]")
    with patch("app.services.mcp_jsonrpc_client.httpx.AsyncClient", return_value=_Client(response=response)):
        with pytest.raises(MCPCallFailure) as raised:
            await mcp_call_tool(provider_url="https://mcp.example", session_id="s", tool_name="search")
    assert raised.value.mcp_failure["kind"] == "protocol"
