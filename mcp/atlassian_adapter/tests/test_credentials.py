import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import json

MCP_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MCP_ROOT))
spec = importlib.util.spec_from_file_location("atlassian_adapter_under_test", MCP_ROOT / "atlassian_adapter/server.py")
server = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"mcp_atlassian.servers.main": SimpleNamespace(main_mcp=MagicMock())}):
    spec.loader.exec_module(server)


def arguments(payload, auth_type="token", url="https://jira.example"):
    return {"issue_key": "TEST-1", "instance_context": {
        "credentials": payload, "auth_type": auth_type, "data_instance_url": url,
    }}


class RequestCredentialsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env_patch = patch.dict("os.environ", {"ENV": "local"})
        self.env_patch.start()
        self.raw_patch = patch.object(server, "ALLOW_RAW_CREDENTIALS", True)
        self.raw_patch.start()

    def tearDown(self):
        self.raw_patch.stop()
        self.env_patch.stop()

    async def test_product_pat_headers_and_data_connector_url(self):
        for tool, product in (("jira_get_issue", "Jira"), ("confluence_get_page", "Confluence")):
            with self.subTest(tool=tool):
                headers, _ = await server._resolve_auth({"name": tool, "arguments": arguments({
                    "token": "request-secret", "base_url": "https://old.example",
                })})
                self.assertEqual(headers[f"X-Atlassian-{product}-Personal-Token"], "request-secret")
                self.assertEqual(headers[f"X-Atlassian-{product}-Url"], "https://jira.example")

    async def test_legacy_api_token_pat(self):
        headers, _ = await server._resolve_auth({"name": "jira_get_issue", "arguments": arguments({"api_token": "pat"})})
        self.assertEqual(headers["X-Atlassian-Jira-Personal-Token"], "pat")

    async def test_basic_and_oauth(self):
        headers, _ = await server._resolve_auth({"name": "jira_get_issue", "arguments": arguments(
            {"username": "alice", "password": "secret"}, "basic",
        )})
        self.assertEqual(headers["Authorization"], "Basic YWxpY2U6c2VjcmV0")
        headers, _ = await server._resolve_auth({"name": "jira_get_issue", "arguments": arguments(
            {"access_token": "oauth-secret"}, "oauth",
        )})
        self.assertEqual(headers["Authorization"], "Bearer oauth-secret")

    async def test_broker_is_authoritative_even_when_raw_credentials_present(self):
        args = arguments({"token": "raw-secret"})
        args["instance_context"]["credential_access"] = {"token": "signed", "resolve_url": "https://broker.example"}
        resolved = SimpleNamespace(payload={"token": "broker-secret"}, auth_type="token")
        with patch("helpers.adapter_auth.SecretBrokerClient.resolve", AsyncMock(return_value=resolved)):
            headers, _ = await server._resolve_auth({"name": "jira_get_issue", "arguments": args})
        self.assertEqual(headers["X-Atlassian-Jira-Personal-Token"], "broker-secret")
        with patch("helpers.adapter_auth.SecretBrokerClient.resolve", AsyncMock(side_effect=ValueError("resolve failed"))):
            with self.assertRaises(ValueError):
                await server._resolve_auth({"name": "jira_get_issue", "arguments": args})

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
        gateway = server.MCPAdapter(server.AdapterConfig(
            policy=server.ToolPolicy(frozenset({"jira_get_issue"})),
            auth_profile=server.AuthProfile(kind="atlassian"),
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
            await server._resolve_auth({"name": "jira_get_issue", "arguments": arguments({"token": "must-not-use"}, "basic")})


if __name__ == "__main__":
    unittest.main()
