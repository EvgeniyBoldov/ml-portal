import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from helpers.adapter_policy import ToolPolicy
from helpers.mcp_adapter import AdapterConfig, MCPAdapter
from helpers.secret_broker import ResolvedCredential


@pytest.mark.asyncio
async def test_adapter_returns_diagnostic_without_exception_secret():
    gateway = MCPAdapter(AdapterConfig(policy=ToolPolicy(
        frozenset({'read'}), {'read': {'x-runtime': {'risk_level': 'safe'}}},
    )))
    gateway.sessions['session'] = time.monotonic() + 60
    credential = ResolvedCredential('cred', 'data', 'token', 'user', {'token': 'private'}, 0)
    with patch('helpers.mcp_adapter.resolve_request_credential', AsyncMock(return_value=credential)), patch.object(
        gateway, '_forward', AsyncMock(side_effect=ValueError('private response body')),
    ):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url='http://adapter') as client:
            response = await client.post('/', headers={'mcp-session-id': 'session', 'x-portal-request-id': 'call-1'}, json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'read'},
            })
    assert response.json()['error']['data'] == {
        'request_id': 'call-1', 'stage': 'upstream_request', 'error_type': 'ValueError',
    }
    assert 'private' not in response.text
