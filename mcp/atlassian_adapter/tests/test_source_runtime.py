from __future__ import annotations

import asyncio
import base64
import os
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import requests
from requests.exceptions import InvalidURL

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
pytest.importorskip("mcp_atlassian")
from atlassian_adapter.source_runtime import (
    PortalAtlassianAdapter, SourceBoundAdapter, build_source_client, build_upstream_app, source_url,
)
from helpers.adapter_policy import ToolPolicy
from helpers.adapter_auth import AuthProfile
from helpers.mcp_adapter import AdapterConfig
from helpers.secret_broker import ResolvedCredential


def credential(kind="token", url="http://10.100.200.20/jira/rest/api/2", instance="data"):
    payload = {"token": "pat-secret"} if kind == "token" else {"email": "alice@example.org", "api_token": " secret:password "}
    return ResolvedCredential("credential", instance, kind, "user", payload, 123, url)


@pytest.mark.parametrize("kind", ["token", "basic"])
def test_native_client_uses_broker_source_and_exact_auth_without_env(kind, monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://wrong-global.invalid")
    client = build_source_client(credential(kind), "jira_get_issue")
    try:
        assert client.url == "http://10.100.200.20/jira"
        prepared = client.session.prepare_request(requests.Request("GET", client.url + "/rest/api/2/issue/TEST-1"))
        expected = "Bearer pat-secret" if kind == "token" else "Basic " + base64.b64encode(b"alice@example.org: secret:password ").decode()
        assert prepared.headers["Authorization"] == expected
        assert client.session.trust_env is False
        assert all(isinstance(adapter, SourceBoundAdapter) for adapter in client.session.adapters.values())
    finally:
        client.session.close()


def test_registered_url_wins_over_untrusted_call_url():
    gateway = PortalAtlassianAdapter(AdapterConfig())
    args = {"url": "http://evil.invalid", "instance_context": {
        "data_instance_id": "data", "data_instance_url": "http://evil.invalid", "config": {"jira_url": "http://evil.invalid"},
    }}
    resolved = credential()
    resolved.payload["jira_url"] = "http://evil.invalid"
    assert gateway._source_url(args, resolved, "jira_get_issue") == "http://10.100.200.20/jira"
    with pytest.raises(ValueError, match="does not match"):
        gateway._source_url({"instance_context": {"data_instance_id": "another-data"}}, resolved, "jira_get_issue")
    resolved.source_url = ""
    with pytest.raises(ValueError, match="Broker did not return"):
        gateway._source_url(args, resolved, "jira_get_issue")


@pytest.mark.parametrize("url", [
    "http://evil.invalid/jira/rest/api/2/issue/TEST-1", "http://10.100.200.20:8080/jira/rest/api/2",
    "http://10.100.200.20/outside", "http://10.100.200.20/jira/%2e%2e/admin",
])
def test_transport_rejects_urls_outside_the_registered_source(url):
    adapter = SourceBoundAdapter("http://10.100.200.20/jira")
    prepared = requests.Request("GET", url).prepare()
    with pytest.raises(InvalidURL, match="outside"):
        adapter.send(prepared)


def test_transport_permits_registered_private_source():
    adapter = SourceBoundAdapter("http://10.100.200.20/jira")
    prepared = requests.Request("GET", "http://10.100.200.20/jira/rest/api/2/issue/TEST-1").prepare()
    with patch("requests.adapters.HTTPAdapter.send", return_value="ok") as send:
        assert adapter.send(prepared) == "ok"
    send.assert_called_once()


@pytest.mark.parametrize("value", ["file:///etc/passwd", "http://user:password@jira.example", "https://jira.example?token=x", ""])
def test_source_url_rejects_unsafe_configuration(value):
    with pytest.raises(ValueError):
        source_url(value)


@pytest.mark.asyncio
async def test_real_upstream_discovery_and_parallel_pat_basic_calls(requests_mock, monkeypatch):
    # The pinned upstream and its actual tools/SDKs run here; only Jira HTTP is mocked.
    for key in ("JIRA_URL", "CONFLUENCE_URL", "JIRA_PERSONAL_TOKEN", "CONFLUENCE_PERSONAL_TOKEN", "MCP_ALLOWED_URL_DOMAINS"):
        monkeypatch.delenv(key, raising=False)
    before_env = dict(os.environ)
    upstream = build_upstream_app()
    gateway = PortalAtlassianAdapter(AdapterConfig(
        name="integration-atlassian", policy=ToolPolicy(frozenset({"jira_get_issue"}), {"jira_get_issue": {"x-runtime": {"risk_level": "safe"}}}),
        auth_profile=AuthProfile(),
    ), upstream_app=upstream)
    observed = []
    def jira_response(request, context):
        observed.append((request.url, request.headers.get("Authorization")))
        if "/field" in request.path:
            return []
        return {"id": "1", "key": "TEST-1", "fields": {
            "summary": "Test issue", "description": "Hello", "status": {"name": "Open"},
            "issuetype": {"name": "Task"}, "project": {"key": "TEST", "name": "Test"},
        }}
    requests_mock.get(__import__("requests_mock").ANY, json=jira_response)
    original_client = httpx.AsyncClient
    def broker_response(request):
        kind = request.headers["Authorization"].removeprefix("Bearer ")
        resolved = credential(kind, "http://10.100.200.20/jira" if kind == "token" else "https://jira-basic.example/context", kind)
        return httpx.Response(200, json={
            "credential_id": resolved.credential_id, "instance_id": resolved.instance_id,
            "auth_type": resolved.auth_type, "owner_type": "user", "payload": resolved.payload,
            "source_url": resolved.source_url, "expires_at": 123,
        })
    def broker_http_client(**kwargs):
        if kwargs.get("transport") is None:
            kwargs["transport"] = httpx.MockTransport(broker_response)
        return original_client(**kwargs)
    async with upstream.router.lifespan_context(upstream):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://adapter") as client:
            init = await client.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            headers = {"mcp-session-id": init.headers["mcp-session-id"]}
            listing = await client.post("/", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            assert [tool["name"] for tool in listing.json()["result"]["tools"]] == ["jira_get_issue"]
            async def call(kind):
                return await client.post("/", headers=headers, json={"jsonrpc": "2.0", "id": kind, "method": "tools/call", "params": {
                    "name": "jira_get_issue", "arguments": {
                        "issue_key": "TEST-1", "comment_limit": 0, "instance_context": {
                            "data_instance_id": kind, "data_instance_url": "http://wrong-untrusted-source.invalid",
                            "credential_access": {"token": kind, "resolve_url": "http://api:8000/api/v1/internal/mcp/credentials/resolve"},
                        },
                    },
                }})
            with patch("helpers.secret_broker.httpx.AsyncClient", broker_http_client):
                responses = await asyncio.gather(call("token"), call("basic"))
            for response in responses:
                result = response.json()
                assert "error" not in result, result
                assert not result["result"].get("isError"), result
    assert observed
    assert {url.split('/')[2] for url, _ in observed} == {"10.100.200.20", "jira-basic.example"}
    for url, auth in observed:
        assert auth == ("Bearer pat-secret" if "10.100.200.20" in url else "Basic " + base64.b64encode(b"alice@example.org: secret:password ").decode())
    # No source URLs, credentials or allowlists were written into process env.
    assert dict(os.environ) == before_env


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "category"), [
    (400, "input"), (401, "auth"), (403, "access"), (429, "rate_limit"), (503, "availability"),
])
async def test_confluence_source_failures_survive_native_server_and_adapter(
    requests_mock, monkeypatch, caplog, status, category,
):
    """The pinned server's MCP error retains source HTTP diagnostics and category."""
    for key in ("JIRA_URL", "CONFLUENCE_URL", "JIRA_PERSONAL_TOKEN", "CONFLUENCE_PERSONAL_TOKEN", "MCP_ALLOWED_URL_DOMAINS"):
        monkeypatch.delenv(key, raising=False)
    title = "Какие задачи решает ML? (Часть 1. Классический ML)"
    query = f'"{title}"'
    observed_cql = []

    def reject_cql(request, context):
        cql = parse_qs(urlsplit(request.url).query).get("cql", [""])[0]
        observed_cql.append(cql)
        message = f"Could not parse cql : {cql}" if status == 400 else "The source rejected the request."
        return {"message": message}

    requests_mock.get(
        __import__("requests_mock").ANY,
        status_code=status,
        json=reject_cql,
    )
    upstream = build_upstream_app()
    gateway = PortalAtlassianAdapter(AdapterConfig(
        name="integration-confluence",
        policy=ToolPolicy(frozenset({"confluence_search"}), {
            "confluence_search": {"x-runtime": {"risk_level": "safe"}},
        }),
    ), upstream_app=upstream)
    original_client = httpx.AsyncClient

    def broker_response(request):
        resolved = ResolvedCredential(
            "credential", "data", "token", "user", {"token": "pat-secret"}, 123,
            "https://wiki.example/confluence",
        )
        return httpx.Response(200, json={
            "credential_id": resolved.credential_id, "instance_id": resolved.instance_id,
            "auth_type": resolved.auth_type, "owner_type": "user", "payload": resolved.payload,
            "source_url": resolved.source_url, "expires_at": 123,
        })

    def broker_http_client(**kwargs):
        if kwargs.get("transport") is None:
            kwargs["transport"] = httpx.MockTransport(broker_response)
        return original_client(**kwargs)

    async with upstream.router.lifespan_context(upstream):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://adapter") as client:
            initialized = await client.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            headers = {"mcp-session-id": initialized.headers["mcp-session-id"]}
            payload = {
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": "confluence_search", "arguments": {
                    "query": query,
                    "instance_context": {"data_instance_id": "data", "credential_access": {
                        "token": "access-jwt", "resolve_url": "http://api:8000/api/v1/internal/mcp/credentials/resolve",
                    }},
                }},
            }
            with patch("helpers.secret_broker.httpx.AsyncClient", broker_http_client):
                response = await client.post("/", headers=headers, json=payload)
    result = response.json()["result"]
    assert result["isError"] is True
    failure = result["_meta"]["portal.failure"]
    assert failure["kind"] == "tool"
    assert failure["category"] == category
    assert observed_cql
    assert f'siteSearch ~ ""{title}""' in observed_cql[0]
    assert failure["details"]["source_failures"][-1]["http_status"] == status
    if status == 400:
        assert "Could not parse cql" in failure["message"]
        captured = failure["details"]["source_failures"]
        assert any(observed_cql[0] in str(item["response"]) for item in captured)
        assert any(observed_cql[-1] in str(item["response"]) for item in captured)
    assert "access-jwt" not in response.text
    assert "pat-secret" not in response.text
    assert title not in caplog.text
    assert "Could not parse cql" not in caplog.text


@pytest.mark.asyncio
async def test_caller_cannot_use_a_forged_broker():
    gateway = PortalAtlassianAdapter(AdapterConfig())
    args = {"instance_context": {"credential_access": {
        "token": "fake", "resolve_url": "http://attacker.invalid/pretend-broker",
    }}}
    with patch("helpers.adapter_auth.SecretBrokerClient.resolve", AsyncMock()) as resolve:
        with pytest.raises(ValueError, match="configured Portal broker"):
            await gateway._resolve_credential(args, "request", "jira_get_issue")
    resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancellation_closes_client_and_clears_request_context():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from atlassian_adapter.source_runtime import _current_client
    fake = SimpleNamespace(product="jira", url="http://jira.internal", session=SimpleNamespace(close=Mock()), source_failures=[])
    gateway = PortalAtlassianAdapter(AdapterConfig())
    with patch("atlassian_adapter.source_runtime.build_source_client", return_value=fake):
        with pytest.raises(asyncio.CancelledError):
            async with gateway._upstream_context(credential(), "jira_get_issue"):
                assert _current_client.get() is fake
                raise asyncio.CancelledError()
    assert _current_client.get() is None
    fake.session.close.assert_called_once()


def test_redirect_is_blocked_before_credentials_can_leave_source(requests_mock):
    client = build_source_client(credential(), "jira_get_issue")
    url = "http://10.100.200.20/jira/rest/api/2/issue/TEST-1"
    requests_mock.get(url, status_code=302, headers={"Location": "http://attacker.invalid/"})
    try:
        with pytest.raises(InvalidURL, match="Redirects"):
            client.session.get(url)
        assert len(requests_mock.request_history) == 1
    finally:
        client.session.close()


@pytest.mark.parametrize("product", ["jira", "confluence"])
@pytest.mark.parametrize("auth_type, payload, header", [
    ("oauth", {"access_token": "oauth-secret"}, ("Authorization", "Bearer oauth-secret")),
    ("api_key", {"api_key": "api-key-secret"}, ("X-API-Key", "api-key-secret")),
])
def test_declared_external_schemes_are_preserved(product, auth_type, payload, header):
    resolved = ResolvedCredential("c", "d", auth_type, "user", payload, 123, "https://source.example/context")
    client = build_source_client(resolved, product + "_get_issue")
    try:
        prepared = client.session.prepare_request(requests.Request("GET", client.url + "/rest/api/2"))
        assert prepared.headers[header[0]] == header[1]
    finally:
        client.session.close()


@pytest.mark.asyncio
async def test_cancellation_during_client_preparation_closes_late_session():
    import threading
    from types import SimpleNamespace
    from unittest.mock import Mock
    ready, release = threading.Event(), threading.Event()
    fake = SimpleNamespace(session=SimpleNamespace(close=Mock()), source_failures=[])
    def prepare(*args):
        ready.set()
        release.wait(timeout=5)
        return fake
    gateway = PortalAtlassianAdapter(AdapterConfig())
    async def enter_context():
        async with gateway._upstream_context(credential(), "jira_get_issue"):
            pytest.fail("Cancelled preparation must not enter upstream context")
    with patch("atlassian_adapter.source_runtime.build_source_client", prepare):
        task = asyncio.create_task(enter_context())
        await asyncio.to_thread(ready.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()
        for _ in range(100):
            if fake.session.close.called:
                break
            await asyncio.sleep(.01)
    fake.session.close.assert_called_once()


def test_transport_rejects_host_header_override():
    adapter = SourceBoundAdapter("http://10.100.200.20/jira")
    prepared = requests.Request("GET", "http://10.100.200.20/jira/rest/api/2", headers={"Host": "attacker.invalid"}).prepare()
    with pytest.raises(InvalidURL, match="Host header"):
        adapter.send(prepared)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["token", "basic"])
async def test_real_confluence_tool_uses_bound_source(kind, requests_mock):
    upstream = build_upstream_app()
    gateway = PortalAtlassianAdapter(AdapterConfig(
        policy=ToolPolicy(frozenset({"confluence_get_page"}), {"confluence_get_page": {"x-runtime": {"risk_level": "safe"}}}),
    ), upstream_app=upstream)
    observed = []
    def page(request, context):
        observed.append((request.url, request.headers.get("Authorization")))
        return {"id": "123", "type": "page", "title": "Test page", "status": "current",
                "space": {"key": "TEST", "name": "Test"},
                "body": {"storage": {"value": "<p>Hello</p>", "representation": "storage"}},
                "version": {"number": 1}, "_links": {"webui": "/pages/123"}}
    requests_mock.get(__import__("requests_mock").ANY, json=page)
    resolved = credential(kind, "http://10.100.200.21/wiki/rest/api")
    with patch.object(gateway, "_resolve_credential", AsyncMock(return_value=resolved)):
        async with upstream.router.lifespan_context(upstream):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://adapter") as client:
                init = await client.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
                response = await client.post("/", headers={"mcp-session-id": init.headers["mcp-session-id"]}, json={
                    "jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                        "name": "confluence_get_page", "arguments": {
                            "page_id": "123", "include_metadata": False, "convert_to_markdown": False,
                        },
                    },
                })
                result = response.json()
                assert "error" not in result, result
                assert not result["result"].get("isError"), result
    assert observed
    for url, auth in observed:
        assert url.startswith("http://10.100.200.21/wiki/")
        assert auth == ("Bearer pat-secret" if kind == "token" else "Basic " + base64.b64encode(b"alice@example.org: secret:password ").decode())
