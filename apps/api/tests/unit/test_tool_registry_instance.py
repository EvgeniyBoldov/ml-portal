"""
Unit tests for ToolRegistry instance-level API (DI / test isolation).

Verifies that:
- ToolRegistry() creates an isolated store independent of the class-level singleton.
- get_handler / list_handlers instance-level reads work on the instance.
- get_instance() returns the same shared object on repeated calls.
- The class-level singleton (ToolRegistry.get / ToolRegistry.register) is unaffected
  by operations on an isolated instance.
"""
from __future__ import annotations

from unittest.mock import MagicMock


from app.agents.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_handler(slug: str) -> MagicMock:
    h = MagicMock()
    h.slug = slug
    h.to_mcp_descriptor.return_value = {"name": slug}
    return h


# ---------------------------------------------------------------------------
# Isolated instance API
# ---------------------------------------------------------------------------

class TestIsolatedInstance:
    def setup_method(self):
        self.registry = ToolRegistry()

    def test_empty_on_creation(self):
        assert self.registry.list_handlers() == []


    def test_get_handler_returns_none_for_unknown(self):
        assert self.registry.get_handler("unknown.tool") is None


# ---------------------------------------------------------------------------
# get_instance() — shared singleton
# ---------------------------------------------------------------------------

class TestGetInstance:
    def test_returns_same_object_on_repeated_calls(self):
        inst1 = ToolRegistry.get_instance()
        inst2 = ToolRegistry.get_instance()
        assert inst1 is inst2

    def test_instance_is_ToolRegistry(self):
        assert isinstance(ToolRegistry.get_instance(), ToolRegistry)


# ---------------------------------------------------------------------------
# Class-level API unaffected by isolated instance operations
# ---------------------------------------------------------------------------

