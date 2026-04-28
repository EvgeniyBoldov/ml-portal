"""
Unit tests for ToolRegistry instance-level API (DI / test isolation).

Verifies that:
- ToolRegistry() creates an isolated store independent of the class-level singleton.
- register_handler / get_handler / list_handlers / clear_handlers work on the instance.
- get_instance() returns the same shared object on repeated calls.
- The class-level singleton (ToolRegistry.get / ToolRegistry.register) is unaffected
  by operations on an isolated instance.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

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

    def test_register_and_get_handler(self):
        h = _make_handler("my.tool")
        self.registry.register_handler(h)
        assert self.registry.get_handler("my.tool") is h

    def test_get_handler_returns_none_for_unknown(self):
        assert self.registry.get_handler("unknown.tool") is None

    def test_list_handlers_returns_all(self):
        h1 = _make_handler("tool.a")
        h2 = _make_handler("tool.b")
        self.registry.register_handler(h1)
        self.registry.register_handler(h2)
        slugs = {h.slug for h in self.registry.list_handlers()}
        assert slugs == {"tool.a", "tool.b"}

    def test_clear_handlers_empties_store(self):
        self.registry.register_handler(_make_handler("tool.x"))
        self.registry.clear_handlers()
        assert self.registry.list_handlers() == []

    def test_overwrite_existing_handler(self):
        h1 = _make_handler("dup.tool")
        h2 = _make_handler("dup.tool")
        self.registry.register_handler(h1)
        self.registry.register_handler(h2)
        assert self.registry.get_handler("dup.tool") is h2

    def test_isolated_from_other_instances(self):
        other = ToolRegistry()
        self.registry.register_handler(_make_handler("isolated.tool"))
        assert other.get_handler("isolated.tool") is None


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

class TestClassLevelUnaffected:
    def setup_method(self):
        self.isolated = ToolRegistry()

    def test_isolated_register_does_not_pollute_class_store(self):
        slug = "class.pollution.test"
        self.isolated.register_handler(_make_handler(slug))
        assert ToolRegistry.get(slug) is None

    def test_isolated_clear_does_not_reset_class_store(self):
        ToolRegistry.register(_make_handler("class.level.handler"))
        self.isolated.register_handler(_make_handler("instance.level.handler"))
        self.isolated.clear_handlers()
        assert ToolRegistry.get("class.level.handler") is not None
        ToolRegistry.clear()  # cleanup
