from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import json

MCP_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MCP_ROOT))
from helpers.adapter_auth import AuthProfile, data_source_url, resolve_request_credential, upstream_auth_headers
from helpers.adapter_policy import ToolPolicy
from helpers.mcp_adapter import AdapterConfig, MCPAdapter


async def resolve_headers(params):
    """Exercise the shared broker resolver and header codec independently."""
    args = params["arguments"]
    resolved = await resolve_request_credential(args, allow_raw=True)
    return upstream_auth_headers(
        resolved, profile=AuthProfile(kind="atlassian"), tool_name=params["name"],
        target_url=data_source_url(args, resolved.payload, tool_name=params["name"]),
    ), args


def arguments(payload, auth_type="token", url="https://jira.example"):
    return {"issue_key": "TEST-1", "instance_context": {
        "credentials": payload, "auth_type": auth_type, "data_instance_url": url,
    }}


class RequestCredentialsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env_patch = patch.dict("os.environ", {"ENV": "local"})
        self.env_patch.start()

    def tearDown(self):
        self.env_patch.stop()

    async def test_product_pat_headers_and_data_connector_url(self):
        for tool, product in (("jira_get_issue", "Jira"), ("confluence_get_page", "Confluence")):
            with self.subTest(tool=tool):
                headers, _ = await resolve_headers({"name": tool, "arguments": arguments({
                    "token": "request-secret", "base_url": "https://old.example",
                })})
                self.assertEqual(headers[f"X-Atlassian-{product}-Personal-Token"], "request-secret")
                self.assertEqual(headers[f"X-Atlassian-{product}-Url"], "https://jira.example")

    async def test_legacy_api_token_pat(self):
        headers, _ = await resolve_headers({"name": "jira_get_issue", "arguments": arguments({"api_token": "pat"})})
        self.assertEqual(headers["X-Atlassian-Jira-Personal-Token"], "pat")

    async def test_basic_and_oauth(self):
        headers, _ = await resolve_headers({"name": "jira_get_issue", "arguments": arguments(
            {"username": "alice", "password": "secret"}, "basic",
        )})
        self.assertEqual(headers["Authorization"], "Basic YWxpY2U6c2VjcmV0")
        headers, _ = await resolve_headers({"name": "jira_get_issue", "arguments": arguments(
            {"access_token": "oauth-secret"}, "oauth",
        )})
        self.assertEqual(headers["Authorization"], "Bearer oauth-secret")

    async def test_broker_is_authoritative_even_when_raw_credentials_present(self):
        args = arguments({"token": "raw-secret"})
        args["instance_context"]["credential_access"] = {"token": "signed", "resolve_url": "https://broker.example"}
        resolved = SimpleNamespace(payload={"token": "broker-secret"}, auth_type="token")
        with patch("helpers.adapter_auth.SecretBrokerClient.resolve", AsyncMock(return_value=resolved)):
            headers, _ = await resolve_headers({"name": "jira_get_issue", "arguments": args})
        self.assertEqual(headers["X-Atlassian-Jira-Personal-Token"], "broker-secret")
        with patch("helpers.adapter_auth.SecretBrokerClient.resolve", AsyncMock(side_effect=ValueError("resolve failed"))):
            with self.assertRaises(ValueError):
                await resolve_headers({"name": "jira_get_issue", "arguments": args})

    async def test_forwarding_strips_credentials_and_isolates_requests(self):
        import httpx
        from helpers.secret_broker import ResolvedCredential
        seen = []
        async def upstream(request):
            payload = json.loads(request.content)
            if payload["method"] == "notifications/initialized":
                return httpx.Response(202)
            if payload["method"] == "tools/call":
                seen.append((payload, request.headers))
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": payload["id"], "result": {}})
        gateway = MCPAdapter(AdapterConfig(
            policy=ToolPolicy(frozenset({"jira_get_issue"}), {"jira_get_issue": {"x-runtime": {"risk_level": "safe"}}}),
            auth_profile=AuthProfile(kind="atlassian"),
        ), transport=httpx.MockTransport(upstream))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=gateway), base_url="http://adapter") as client:
            init = await client.post("/", json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
            headers = {"mcp-session-id": init.headers["mcp-session-id"]}
            for secret in ("first-secret", "second-secret"):
                resolved = ResolvedCredential("c", "d", "token", "user", {"token": secret}, 123)
                with patch("helpers.mcp_adapter.resolve_request_credential", AsyncMock(return_value=resolved)):
                    response = await client.post("/", headers=headers, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                        "name": "jira_get_issue", "arguments": arguments({"token": "must-strip"}),
                    }})
                self.assertIn("result", response.json())
                payload, forwarded_headers = seen[-1]
                self.assertEqual(forwarded_headers["X-Atlassian-Jira-Personal-Token"], secret)
                self.assertEqual(payload["params"]["arguments"], {"issue_key": "TEST-1"})

    async def test_auth_type_is_not_inferred_from_a_token_field(self):
        with self.assertRaises(ValueError):
            await resolve_headers({"name": "jira_get_issue", "arguments": arguments({"token": "must-not-use"}, "basic")})


if __name__ == "__main__":
    unittest.main()
