import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from portal_mcp_contract import MCPFailure, MCPFailureCategory, MCPFailureKind

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
    failure = response.json()['error']['data']
    assert failure['version'] == 1
    assert failure['kind'] == 'protocol'
    assert failure['category'] == 'unknown'
    assert failure['code'] == 'ValueError'
    assert failure['message'] == '[redacted] response body'
    assert failure['details']['exception_type'] == 'ValueError'
    assert failure['request_id'] == 'call-1'
    assert failure['stage'] == 'upstream_request'
    assert failure['user_message'] == 'The source request failed.'
    assert 'private' not in response.text


@pytest.mark.asyncio
async def test_adapter_preserves_normalized_upstream_failure_semantics():
    gateway = MCPAdapter(AdapterConfig(policy=ToolPolicy(
        frozenset({'read'}), {'read': {'x-runtime': {'risk_level': 'safe'}}},
    )))
    gateway.sessions['session'] = time.monotonic() + 60
    credential = ResolvedCredential('cred', 'data', 'token', 'user', {'token': 'private'}, 0)
    upstream_failure = MCPFailure(
        kind=MCPFailureKind.RPC,
        category=MCPFailureCategory.AUTH,
        code='credential_rejected',
        message='source rejected credential',
        details={'reason': 'expired'},
        rpc_code=-32001,
        rpc_data={'reason': 'expired'},
    ).bounded_dump()
    with patch('helpers.mcp_adapter.resolve_request_credential', AsyncMock(return_value=credential)), patch.object(
        gateway, '_forward', AsyncMock(return_value={'jsonrpc': '2.0', 'id': 1, 'error': {
            'code': -32001, 'message': 'upstream wrapper', 'data': upstream_failure,
        }}),
    ):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url='http://adapter') as client:
            response = await client.post('/', headers={'mcp-session-id': 'session'}, json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'read'},
            })
    failure = response.json()['error']['data']
    assert failure['category'] == 'auth'
    assert failure['code'] == 'credential_rejected'
    assert failure['message'] == 'source rejected credential'
    assert failure['rpc_code'] == -32001
