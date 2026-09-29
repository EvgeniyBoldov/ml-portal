import sys
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import Response


MCP_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MCP_ROOT))

from netbox import server  # noqa: E402


class SearchObjectTypesTest(unittest.TestCase):
    def test_untyped_search_uses_bounded_vanilla_types(self) -> None:
        self.assertEqual(
            server._search_object_types(None),
            [
                "dcim.device",
                "dcim.rack",
                "dcim.site",
                "ipam.ipaddress",
                "ipam.prefix",
            ],
        )

    def test_explicit_plugin_type_keeps_plugin_route(self) -> None:
        self.assertEqual(
            server._resolve_object_path("dcbox.capacity"),
            "/api/plugins/dcbox/capacitys/",
        )

    def test_explicit_vanilla_type_does_not_use_extras(self) -> None:
        self.assertEqual(
            server._resolve_object_path("dcim.rack"),
            "/api/dcim/racks/",
        )

    def test_ipam_routes_use_netbox_slugs(self) -> None:
        self.assertEqual(server._resolve_object_path("ipam.prefix"), "/api/ipam/prefixes/")
        self.assertEqual(server._resolve_object_path("ipam.ipaddress"), "/api/ipam/ip-addresses/")


class SearchErrorsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        server.SESSIONS.add("test-session")

    async def asyncTearDown(self) -> None:
        server.SESSIONS.discard("test-session")

    async def _call(self, name: str, arguments: dict) -> dict:
        request = SimpleNamespace(json=AsyncMock(return_value={
            "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments},
        }))
        return await server.mcp_root(request, Response(), mcp_session_id="test-session")

    async def test_prefix_filter_uses_correct_endpoint(self) -> None:
        with patch.object(server, "_resolve_runtime_access", new=AsyncMock(return_value=("https://netbox.example", "token"))), \
             patch.object(server, "_netbox_get", new=AsyncMock(return_value={"count": 1, "results": [{"prefix": "10.0.0.0/24"}]})) as get:
            result = await self._call("netbox_get_objects", {
                "object_type": "ipam.prefix", "filters": {"prefix": "10.0.0.0/24"},
            })
        self.assertFalse(result["result"]["isError"])
        self.assertEqual(get.await_args.kwargs["path"], "/api/ipam/prefixes/")
        self.assertEqual(get.await_args.kwargs["params"]["prefix"], "10.0.0.0/24")

    async def test_partial_search_reports_failed_ipam_type(self) -> None:
        async def get(*, path: str, **kwargs: object) -> dict:
            if path == "/api/ipam/prefixes/":
                request = httpx.Request("GET", "https://netbox.example" + path)
                response = httpx.Response(404, request=request)
                raise httpx.HTTPStatusError("not found", request=request, response=response)
            return {"count": 0, "results": []}

        with patch.object(server, "_resolve_runtime_access", new=AsyncMock(return_value=("https://netbox.example", "token"))), \
             patch.object(server, "_netbox_get", new=AsyncMock(side_effect=get)):
            result = await self._call("netbox_search_objects", {"q": "10.0.0.0/24"})
        data = result["result"]["structuredContent"]
        self.assertFalse(result["result"]["isError"])
        self.assertEqual(data["errors"], [{"object_type": "ipam.prefix", "status": 404, "error": "NetBox HTTP error"}])
        self.assertEqual(len(data["results"]), 4)
        self.assertIn("ipam.prefix", result["result"]["content"][0]["text"])

    async def test_all_search_types_failed_is_tool_error(self) -> None:
        with patch.object(server, "_resolve_runtime_access", new=AsyncMock(return_value=("https://netbox.example", "token"))), \
             patch.object(server, "_netbox_get", new=AsyncMock(side_effect=httpx.ConnectError("unavailable"))):
            result = await self._call("netbox_search_objects", {"q": "example", "object_types": ["ipam.prefix"]})
        self.assertTrue(result["result"]["isError"])
        self.assertEqual(result["result"]["structuredContent"]["errors"][0]["object_type"], "ipam.prefix")


if __name__ == "__main__":
    unittest.main()
