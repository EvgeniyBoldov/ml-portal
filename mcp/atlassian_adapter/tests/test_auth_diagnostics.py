from __future__ import annotations

import base64
import logging
from pathlib import Path
import sys

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from atlassian_adapter.diagnostics import AtlassianAuthDiagnostics
from helpers.adapter_auth import AuthProfile, log_authentication_request, upstream_auth_headers
from helpers.secret_broker import ResolvedCredential


@pytest.mark.parametrize("auth_type,payload,expected_headers", [
    ("basic", {"email": "alice@example.org", "api_token": " password:secret "}, {
        "Authorization": "Basic " + base64.b64encode(b"alice@example.org: password:secret ").decode(),
        "X-Atlassian-Jira-Url": "https://jira.example",
    }),
    ("token", {"token": "pat-secret", "username": "unused", "password": "unused"}, {
        "X-Atlassian-Jira-Personal-Token": "pat-secret",
        "X-Atlassian-Jira-Url": "https://jira.example",
    }),
])
def test_auth_contract_and_masked_request_log(caplog, auth_type, payload, expected_headers):
    credential = ResolvedCredential("credential", "instance", auth_type, "user", payload, 0)
    profile = AuthProfile(kind="atlassian")
    headers = upstream_auth_headers(
        credential, profile=profile, tool_name="jira_get_issue", target_url="https://jira.example",
    )
    assert headers == expected_headers
    with caplog.at_level(logging.INFO, logger="mcp.adapter_auth"):
        log_authentication_request(
            credential, profile=profile, headers=headers, request_id="auth-test",
            tool_name="jira_get_issue", target_url="https://jira.example",
        )
    assert "auth_in_body=false" in caplog.text
    assert '"X-Atlassian-Jira-Url": "https://jira.example"' in caplog.text
    if auth_type == "basic":
        assert "username=alice@example.org" in caplog.text
        assert '"Authorization": "Basic ***"' in caplog.text
        assert '"api_token": true' in caplog.text
        assert headers["Authorization"] not in caplog.text
        assert "password:secret" not in caplog.text
    else:
        assert '"X-Atlassian-Jira-Personal-Token": "***"' in caplog.text
        assert "pat-secret" not in caplog.text
        assert "unused" not in caplog.text


@pytest.mark.asyncio
async def test_upstream_private_ip_rejection_is_distinct_from_bad_credentials(caplog):
    async def upstream(scope, receive, send):
        scope = dict(scope)  # Match UserTokenMiddleware's shallow scope copy.
        scope.setdefault("state", {})["auth_validation_error"] = (
            "Forbidden: Invalid Jira URL - DNS for jira.example resolves to non-global IP: "
            "10.100.200.20 token=never-log-secret"
        )
        await send({"type": "http.response.start", "status": 401, "headers": []})
        await send({"type": "http.response.body", "body": b""})
    app = AtlassianAuthDiagnostics(upstream)
    with caplog.at_level(logging.INFO, logger="mcp.atlassian_auth"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://embedded") as client:
            response = await client.post("/mcp", headers={
                "x-portal-request-id": "private-ip-test",
                "X-Atlassian-Jira-Url": "https://jira.example",
                "X-Atlassian-Jira-Personal-Token": "never-log-secret",
            })
    assert response.status_code == 401
    assert "private_ip_blocked" in caplog.text
    assert "request_id=private-ip-test" in caplog.text
    assert "never-log-secret" not in caplog.text


@pytest.mark.asyncio
async def test_upstream_parsed_basic_fields_are_reported_without_values(caplog):
    async def upstream(scope, receive, send):
        scope = dict(scope)  # Match UserTokenMiddleware's shallow scope copy.
        scope.setdefault("state", {}).update({
            "user_atlassian_auth_type": "basic", "user_atlassian_email": "alice@example.org",
            "user_atlassian_api_token": "never-log-secret",
        })
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})
    with caplog.at_level(logging.INFO, logger="mcp.atlassian_auth"):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=AtlassianAuthDiagnostics(upstream)), base_url="http://embedded") as client:
            await client.post("/mcp")
    assert "auth_type=basic" in caplog.text
    assert "username_present=True api_token_present=True token_present=False" in caplog.text
    assert "never-log-secret" not in caplog.text


@pytest.mark.asyncio
async def test_failed_initialize_keeps_auth_header_names_and_masks_values(caplog):
    from unittest.mock import AsyncMock, patch
    from helpers.adapter_policy import ToolPolicy
    from helpers.mcp_adapter import AdapterConfig, MCPAdapter

    sent = []
    async def upstream(request):
        sent.append(request.headers)
        return httpx.Response(401)
    credential = ResolvedCredential("credential", "instance", "token", "user", {"token": "never-log-secret"}, 0)
    gateway = MCPAdapter(AdapterConfig(
        policy=ToolPolicy(frozenset({"jira_get_issue"}), {"jira_get_issue": {"x-runtime": {"risk_level": "safe"}}}),
        auth_profile=AuthProfile(kind="atlassian"),
    ), transport=httpx.MockTransport(upstream))
    with caplog.at_level(logging.INFO):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://adapter") as client:
            init = await client.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            with patch("helpers.mcp_adapter.resolve_request_credential", AsyncMock(return_value=credential)):
                response = await client.post("/", headers={
                    "mcp-session-id": init.headers["mcp-session-id"], "x-portal-request-id": "failed-init",
                }, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                    "name": "jira_get_issue", "arguments": {
                        "instance_context": {"data_instance_url": "https://jira.example"},
                    },
                }})
    assert response.json()["error"]["data"]["stage"] == "upstream_request"
    assert sent[0]["X-Atlassian-Jira-Personal-Token"] == "never-log-secret"
    assert "auth_headers=X-Atlassian-Jira-Personal-Token_X-Atlassian-Jira-Url" in caplog.text
    assert "never-log-secret" not in caplog.text
    assert "never-log-secret" not in response.text
