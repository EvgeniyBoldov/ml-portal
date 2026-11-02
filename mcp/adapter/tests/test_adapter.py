from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from helpers.adapter_auth import AuthProfile, resolve_request_credential, upstream_auth_headers
from helpers.adapter_policy import ToolPolicy
from helpers.mcp_adapter import AdapterConfig, MCPAdapter
from helpers.secret_broker import ResolvedCredential


def credential(auth_type="token", **payload):
    return ResolvedCredential("credential-id", "data-id", auth_type, "user", payload, 123)


@pytest.mark.parametrize("auth_type,payload,expected", [
    ("token", {"token": "pat", "username": "irrelevant", "password": "irrelevant"}, {"Authorization": "Bearer pat"}),
    ("basic", {"username": "alice", "password": "password", "token": "irrelevant"}, {"Authorization": "Basic " + base64.b64encode(b"alice:password").decode()}),
    ("basic", {"username": "alice", "password": " password "}, {"Authorization": "Basic " + base64.b64encode(b"alice: password ").decode()}),
    ("oauth", {"access_token": "oauth", "api_key": "irrelevant"}, {"Authorization": "Bearer oauth"}),
    ("api_key", {"api_key": "key", "token": "irrelevant"}, {"X-API-Key": "key"}),
])
def test_auth_type_is_authoritative(auth_type, payload, expected):
    assert upstream_auth_headers(credential(auth_type, **payload)) == expected


@pytest.mark.parametrize("auth_type,payload", [
    ("basic", {"token": "must-not-be-used"}), ("api_key", {"token": "wrong-field"}),
    ("invalid", {"token": "must-not-be-used"}), ("", {"token": "must-not-be-used"}),
    ("token", {"token": "secret\r\nInjected: bad"}),
])
def test_missing_or_unsupported_auth_never_switches_scheme(auth_type, payload):
    with pytest.raises(ValueError):
        upstream_auth_headers(credential(auth_type, **payload))


def test_profiles_support_netbox_style_tokens_api_key_headers_and_target_url():
    assert upstream_auth_headers(credential(token="pat"), profile=AuthProfile(token_scheme="Token")) == {"Authorization": "Token pat"}
    headers = upstream_auth_headers(credential("api_key", api_key="key"), profile=AuthProfile(api_key_header="X-Service-Key", target_url_header="X-Target"), target_url="https://data.example")
    assert headers == {"X-Service-Key": "key", "X-Target": "https://data.example"}


@pytest.mark.asyncio
async def test_raw_credentials_are_explicit_local_only_and_broker_failure_is_authoritative(monkeypatch):
    args = {"instance_context": {"auth_type": "token", "credentials": {"token": "raw"}}}
    monkeypatch.setenv("ENV", "local")
    with pytest.raises(ValueError):
        await resolve_request_credential(args)
    assert (await resolve_request_credential(args, allow_raw=True)).payload == {"token": "raw"}
    monkeypatch.setenv("ENV", "production")
    with pytest.raises(ValueError):
        await resolve_request_credential(args, allow_raw=True)
    args["instance_context"]["credential_access"] = {"token": "bad", "resolve_url": "http://api/resolve"}
    with patch("helpers.adapter_auth.SecretBrokerClient.resolve", AsyncMock(side_effect=ValueError("invalid broker token"))):
        with pytest.raises(ValueError):
            await resolve_request_credential(args, allow_raw=True)


@pytest.mark.asyncio
async def test_real_broker_http_exchange_passes_only_short_lived_token():
    seen = []
    async def broker(scope, receive, send):
        headers = dict(scope["headers"])
        seen.append((scope["method"], headers.get(b"authorization")))
        body = json.dumps({"credential_id": "c", "instance_id": "data", "auth_type": "basic", "owner_type": "user", "payload": {"username": "alice", "password": "secret"}, "expires_at": 123}).encode()
        await send({"type": "http.response.start", "status": 200, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": body})
    # Exercise the actual SecretBrokerClient HTTP implementation through ASGI.
    original = httpx.AsyncClient
    def client(**kwargs):
        return original(transport=httpx.ASGITransport(app=broker), **kwargs)
    with patch("helpers.secret_broker.httpx.AsyncClient", client):
        result = await resolve_request_credential({"instance_context": {"credential_access": {"token": "short-lived", "resolve_url": "http://api/resolve"}, "auth_type": "token"}})
    assert seen == [("POST", b"Bearer short-lived")]
    assert result.auth_type == "basic"
    assert upstream_auth_headers(result)["Authorization"].startswith("Basic ")


def upstream_transport(seen, *, error=False, paginated=False):
    async def upstream(request):
        body = json.loads(request.content)
        seen.append((body, dict(request.headers)))
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        if body["method"] == "initialize":
            return httpx.Response(200, headers={"mcp-session-id": "upstream-session"}, json={"jsonrpc": "2.0", "id": body["id"], "result": {"protocolVersion": "2024-11-05"}})
        if error:
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "error": {"code": -1, "message": "secret-from-provider"}})
        if body["method"] == "tools/list":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [
                {"name": "read", "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True}},
                {"name": "delete", "inputSchema": {"type": "object"}},
            ], **({"nextCursor": "page2"} if paginated else {})}})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"isError": False, "structuredContent": {"ok": True}}})
    return httpx.MockTransport(upstream)


async def initialize(client):
    response = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    return {"mcp-session-id": response.headers["mcp-session-id"]}


@pytest.mark.asyncio
async def test_gateway_filters_listing_enriches_descriptors_and_blocks_direct_hidden_calls():
    seen = []
    policy = ToolPolicy(frozenset({"read"}), {"read": {"description": "Curated description", "x-runtime": {"credential_scope": "auto"}}})
    gateway = MCPAdapter(AdapterConfig(policy=policy), transport=upstream_transport(seen, paginated=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://adapter") as c:
        headers = await initialize(c)
        result = (await c.post("/", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})).json()["result"]
        assert [t["name"] for t in result["tools"]] == ["read"]
        assert result["nextCursor"] == "page2"
        tool = result["tools"][0]
        assert tool["description"] == "Curated description"
        assert tool["inputSchema"]["x-runtime"]["risk_level"] == "safe"
        assert tool["inputSchema"]["x-runtime"]["credential_scope"] == "auto"
        before = len(seen)
        with patch("helpers.mcp_adapter.resolve_request_credential", AsyncMock()) as resolver:
            r = await c.post("/", headers=headers, json={"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "delete"}})
            assert r.json()["error"]["code"] == -32601
            resolver.assert_not_awaited()
        assert len(seen) == before


@pytest.mark.asyncio
async def test_gateway_broker_credentials_are_isolated_between_concurrent_users():
    seen = []
    gateway = MCPAdapter(AdapterConfig(policy=ToolPolicy(frozenset({"read"}))), transport=upstream_transport(seen))
    async def resolve(args, **kwargs):
        await asyncio.sleep(0)
        return credential(token=args["instance_context"]["credential_access"]["token"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://adapter") as c:
        headers = await initialize(c)
        async def call(secret):
            return await c.post("/", headers=headers, json={"jsonrpc": "2.0", "id": secret, "method": "tools/call", "params": {"name": "read", "arguments": {"query": secret, "url": "https://public-tool-argument", "collection_slug": "portal-source", "credentials": {"token": "must-strip"}, "instance_context": {"credential_access": {"token": secret}}}}})
        with patch("helpers.mcp_adapter.resolve_request_credential", resolve):
            results = await asyncio.gather(call("alice"), call("bob"))
        assert all(r.json()["result"]["structuredContent"] == {"ok": True} for r in results)
    calls = [(body, headers) for body, headers in seen if body["method"] == "tools/call"]
    assert len(calls) == 2
    for body, headers in calls:
        args = body["params"]["arguments"]
        assert args == {"query": body["id"], "url": "https://public-tool-argument"}
        assert headers["authorization"] == "Bearer " + body["id"]
        assert headers["mcp-session-id"] == "upstream-session"
        assert "x-portal-request-id" in headers
    assert all(isinstance(expiry, float) for expiry in gateway.sessions.values())


@pytest.mark.asyncio
async def test_gateway_broker_failure_never_calls_upstream_or_exposes_exception():
    seen = []
    gateway = MCPAdapter(AdapterConfig(policy=ToolPolicy(frozenset({"read"}))), transport=upstream_transport(seen))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://adapter") as c:
        headers = await initialize(c)
        with patch("helpers.mcp_adapter.resolve_request_credential", AsyncMock(side_effect=ValueError("secret-from-broker"))):
            r = await c.post("/", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "read"}})
        assert "error" in r.json()
        assert "secret-from-broker" not in r.text
        assert seen == []


@pytest.mark.asyncio
async def test_gateway_sanitizes_upstream_rpc_errors_and_never_replays_call():
    seen = []
    # Fail only the tool request, after a successful initialize.
    gateway = MCPAdapter(AdapterConfig(policy=ToolPolicy(frozenset({"read"}))), transport=upstream_transport(seen, error=True))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://adapter") as c:
        headers = await initialize(c)
        with patch("helpers.mcp_adapter.resolve_request_credential", AsyncMock(return_value=credential(token="secret"))):
            r = await c.post("/", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "read"}})
        assert "error" in r.json()
        assert "secret-from-provider" not in r.text
    assert sum(body["method"] == "tools/call" for body, _ in seen) == 1


def test_empty_policy_is_closed_and_destructive_hint_wins_over_read_only():
    assert not ToolPolicy().allows("read")
    tool = ToolPolicy().decorate({"name": "read", "annotations": {"readOnlyHint": True, "destructiveHint": True}})
    assert tool["inputSchema"]["x-runtime"]["risk_level"] == "destructive"


def test_sse_notifications_are_ignored_when_selecting_response():
    from helpers.mcp_adapter import parse_response
    body = b'data: {"jsonrpc":"2.0","method":"notifications/progress"}\n\ndata: {"jsonrpc":"2.0","id":2,"result":{}}\n\n'
    assert parse_response(body, 2)["result"] == {}


@pytest.mark.asyncio
async def test_gateway_rejects_expired_sessions_before_secret_resolution():
    gateway = MCPAdapter(AdapterConfig(policy=ToolPolicy(None)))
    gateway.sessions["expired"] = 0
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://adapter") as c:
        with patch("helpers.mcp_adapter.resolve_request_credential", AsyncMock()) as resolver:
            r = await c.post("/", headers={"mcp-session-id": "expired"}, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "read"}})
            assert r.json()["error"]["code"] == -32002
            resolver.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["size", "timeout"])
async def test_gateway_bounds_upstream_responses_and_duration(failure):
    async def upstream(request):
        if failure == "timeout":
            await asyncio.sleep(.1)
        return httpx.Response(200, json={"id": json.loads(request.content)["id"], "result": {"oversized": "x" * 1000}})
    gateway = MCPAdapter(AdapterConfig(policy=ToolPolicy(None), timeout_s=.02 if failure == "timeout" else 1, max_response_bytes=100), transport=httpx.MockTransport(upstream))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://adapter") as c:
        headers = await initialize(c)
        r = await c.post("/", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert "error" in r.json()
        assert "oversized" not in r.text
