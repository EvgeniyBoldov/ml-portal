import sys
from pathlib import Path
import unittest


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


if __name__ == "__main__":
    unittest.main()
