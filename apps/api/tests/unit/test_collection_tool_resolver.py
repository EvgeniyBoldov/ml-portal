from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.collection_tool_resolver import (
    CollectionToolResolutionContext,
    CollectionToolResolver,
)


def _instance(*, config=None, domain=""):
    return SimpleNamespace(config=config or {}, domain=domain, instance_kind="data")


def test_resolve_local_domains_prefers_collection_binding_type():
    instance = _instance(
        config={
            "binding_type": "collection_asset",
            "collection_id": "3b59e0a0-a1d4-4b8d-a4f2-7cdb9de9f35a",
            "collection_type": "table",
        },
        domain="rag",
    )

    domains = CollectionToolResolver._resolve_local_domains(instance)

    assert domains == ["collection.table", "rag"]


def test_resolve_local_domains_avoids_duplicates():
    instance = _instance(
        config={
            "binding_type": "collection_asset",
            "collection_slug": "kb_docs",
            "tenant_id": "58e616fc-acb8-49bb-8655-7f26f1f0fcb4",
            "collection_type": "document",
        },
        domain="collection.document",
    )

    domains = CollectionToolResolver._resolve_local_domains(instance)

    assert domains == ["collection.document"]


def test_resolve_local_domains_falls_back_to_instance_domain():
    instance = _instance(
        config={"provider_kind": "local"},
        domain="sql",
    )

    domains = CollectionToolResolver._resolve_local_domains(instance)

    assert domains == ["sql"]


def test_catalog_tool_supported_for_bound_document_collection():
    instance = _instance(
        config={
            "binding_type": "collection_asset",
            "collection_type": "document",
        },
        domain="collection.document",
    )
    tool = SimpleNamespace(source="local", slug="collection.catalog")
    bound_collection = SimpleNamespace(id="any")

    supported = CollectionToolResolver._is_tool_supported_for_context(
        tool=tool,
        context=CollectionToolResolutionContext(
            instance=instance,
            provider=SimpleNamespace(),
            bound_collection=bound_collection,
            runtime_domain="collection.document",
            provider_kind="local",
            is_service_instance=False,
        ),
    )

    assert supported is True


def test_catalog_tool_supported_for_bound_api_collection():
    instance = _instance(
        config={
            "binding_type": "collection_asset",
            "collection_type": "api",
        },
        domain="collection.api",
    )
    tool = SimpleNamespace(source="local", slug="collection.catalog")
    bound_collection = SimpleNamespace(id="any")

    supported = CollectionToolResolver._is_tool_supported_for_context(
        tool=tool,
        context=CollectionToolResolutionContext(
            instance=instance,
            provider=SimpleNamespace(),
            bound_collection=bound_collection,
            runtime_domain="collection.api",
            provider_kind="local",
            is_service_instance=False,
        ),
    )

    assert supported is True


@pytest.mark.asyncio
async def test_load_discovered_tools_adds_catalog_for_bound_local_collection():
    resolver = CollectionToolResolver(session=SimpleNamespace())
    instance = _instance(
        config={"binding_type": "collection_asset", "collection_type": "table"},
        domain="collection.table",
    )
    provider = SimpleNamespace(
        id="provider-1",
        instance_kind="service",
        config={"provider_kind": "local"},
        connector_type="mcp",
        placement="local",
    )
    local_tool = SimpleNamespace(source="local", slug="collection.search")
    catalog_tool = SimpleNamespace(source="local", slug="collection.catalog")

    resolver._resolve_bound_collection = AsyncMock(return_value=SimpleNamespace(id="collection-1"))
    resolver._load_local_tools_for_provider = AsyncMock(return_value=[local_tool])
    resolver._load_local_collection_catalog_tools = AsyncMock(return_value=[catalog_tool])
    resolver._load_provider_tools = AsyncMock(return_value=[])

    tools = await resolver.load_discovered_tools(instance=instance, provider=provider, include_unpublished=False)

    assert [tool.slug for tool in tools] == ["collection.search", "collection.catalog"]
