from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.routers.admin.tool_instances import (
    _runtime_tool_summary,
)


def _instance(**overrides):
    base = {
        "id": "instance-id",
        "slug": "contracts",
        "domain": "collection.table",
        "config": {},
        "instance_kind": "data",
        "is_data": True,
        "is_active": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _provider(**overrides):
    base = {
        "slug": "mcp-prod",
        "domain": "mcp",
        "id": "provider-id",
        "config": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _tool(**overrides):
    base = {
        "slug": "collection.search",
        "source": "local",
        "name": "Search",
        "description": None,
        "input_schema": {"type": "object"},
        "output_schema": None,
        "domains": ["collection.table"],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_runtime_tool_summary_returns_zero_for_non_data_instance(monkeypatch):
    monkeypatch.setattr(
        "app.services.collection_tool_resolver.CollectionToolResolver._resolve_bound_collection",
        AsyncMock(return_value=None),
    )
    summary = await _runtime_tool_summary(
        db=SimpleNamespace(),
        instance=_instance(instance_kind="service", is_data=False),
    )
    assert summary == (0, 0, [])


@pytest.mark.asyncio
async def test_runtime_tool_summary_builds_counts(monkeypatch):
    instance = _instance()
    provider = _provider()
    discovered_tools = [_tool(slug="collection.search"), _tool(slug="collection.table.search")]

    monkeypatch.setattr(
        "app.api.v1.routers.admin.tool_instances._resolve_provider_instance",
        AsyncMock(return_value=provider),
    )
    monkeypatch.setattr(
        "app.api.v1.routers.admin.tool_instances._load_discovered_tools_for_instance",
        AsyncMock(return_value=discovered_tools),
    )
    monkeypatch.setattr(
        "app.services.collection_tool_resolver.CollectionToolResolver._resolve_bound_collection",
        AsyncMock(return_value=SimpleNamespace(collection_type="table", has_vector_search=True)),
    )
    monkeypatch.setattr(
        "app.agents.capability_resolver.CollectionCapabilityResolver.resolve_for_instance",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    canonical_op_slug="collection.table.search",
                    discovered_tool=discovered_tools[0],
                ),
                SimpleNamespace(
                    canonical_op_slug="collection.table.search",
                    discovered_tool=discovered_tools[1],
                ),
            ]
        ),
    )

    discovered_count, runtime_count, operations = await _runtime_tool_summary(
        db=SimpleNamespace(),
        instance=instance,
    )

    assert discovered_count == 2
    assert runtime_count == 1
    assert len(operations) == 1
