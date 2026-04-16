from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.routers.admin.tool_instances import (
    _materialize_runtime_operations,
    _runtime_tool_summary,
)


def _instance(**overrides):
    base = {
        "slug": "contracts",
        "domain": "collection.table",
        "config": {},
        "instance_kind": "data",
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
        "input_schema": {},
        "domains": ["collection.table"],
        "semantic_override": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_materialize_runtime_operations_deduplicates_and_applies_discovered_override():
    instance = _instance()
    provider = _provider()
    discovered_tools = [
        _tool(
            slug="collection.search",
            semantic_override={"risk_level": "high", "requires_confirmation": True},
        ),
        _tool(slug="collection.table.search"),
        _tool(slug="collection.unknown"),
    ]

    operations = _materialize_runtime_operations(
        instance=instance,
        provider=provider,
        discovered_tools=discovered_tools,
    )

    assert len(operations) == 1
    op = operations[0]
    assert op.operation == "collection.table.search"
    assert op.operation_slug == "instance.contracts.collection.table.search"
    assert op.provider_instance_slug == "mcp-prod"
    assert op.risk_level == "high"
    assert op.requires_confirmation is True


@pytest.mark.asyncio
async def test_runtime_tool_summary_returns_zero_for_non_data_instance():
    summary = await _runtime_tool_summary(db=SimpleNamespace(), instance=_instance(instance_kind="service"))
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

    discovered_count, runtime_count, operations = await _runtime_tool_summary(
        db=SimpleNamespace(),
        instance=instance,
    )

    assert discovered_count == 2
    assert runtime_count == 1
    assert len(operations) == 1
