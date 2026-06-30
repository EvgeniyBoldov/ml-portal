from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.collection_tool_resolver import (
    CollectionToolResolutionContext,
    CollectionToolResolver,
)


def _instance(*, config=None, domain=""):
    return SimpleNamespace(config=config or {}, domain=domain, instance_kind="data")


def test_resolve_local_domains_uses_instance_domain_only():
    instance = _instance(config={}, domain="rag")

    domains = CollectionToolResolver._resolve_local_domains(instance)

    assert domains == ["rag"]


def test_resolve_local_domains_avoids_duplicates():
    instance = _instance(config={}, domain="collection.document")

    domains = CollectionToolResolver._resolve_local_domains(instance)

    assert domains == ["collection.document"]


def test_resolve_local_domains_falls_back_to_instance_domain():
    instance = _instance(
        config={"provider_kind": "local"},
        domain="sql",
    )

    domains = CollectionToolResolver._resolve_local_domains(instance)

    assert domains == ["sql"]


def test_collection_catalog_tool_is_supported_for_collection_bound_local_provider():
    instance = _instance(config={}, domain="collection.document")
    tool = SimpleNamespace(source="local", slug="collection.info")
    bound_collection = SimpleNamespace(id="any", collection_type="document")

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


def test_collection_catalog_tool_is_supported_for_api_collection_provider():
    instance = _instance(config={}, domain="collection.api")
    tool = SimpleNamespace(source="local", slug="collection.info")
    bound_collection = SimpleNamespace(id="any", collection_type="api")

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


def test_text_search_tool_supported_for_bound_template_collection():
    instance = _instance(config={}, domain="collection.template")
    tool = SimpleNamespace(source="local", slug="collection.template.search")
    bound_collection = SimpleNamespace(id="any", collection_type="template", has_vector_search=True)

    supported = CollectionToolResolver._is_tool_supported_for_context(
        tool=tool,
        context=CollectionToolResolutionContext(
            instance=instance,
            provider=SimpleNamespace(),
            bound_collection=bound_collection,
            runtime_domain="collection.template",
            provider_kind="local",
            is_service_instance=False,
        ),
    )

    assert supported is True


def test_text_search_tool_rejected_for_template_without_vector_search():
    instance = _instance(config={}, domain="collection.template")
    tool = SimpleNamespace(source="local", slug="collection.template.search")
    bound_collection = SimpleNamespace(id="any", collection_type="template", has_vector_search=False)

    supported = CollectionToolResolver._is_tool_supported_for_context(
        tool=tool,
        context=CollectionToolResolutionContext(
            instance=instance,
            provider=SimpleNamespace(),
            bound_collection=bound_collection,
            runtime_domain="collection.template",
            provider_kind="local",
            is_service_instance=False,
        ),
    )

    assert supported is False


@pytest.mark.asyncio
async def test_load_discovered_tools_adds_builtin_collection_info_for_bound_local_collection(monkeypatch):
    resolver = CollectionToolResolver(session=SimpleNamespace())
    instance = _instance(
        config={},
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
    resolver._resolve_bound_collection = AsyncMock(
        return_value=SimpleNamespace(id="collection-1", collection_type="table", has_vector_search=False)
    )
    resolver._load_local_tools_for_provider = AsyncMock(return_value=[local_tool])
    resolver._load_provider_tools = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.collection_tool_resolver.ToolRegistry.list_all",
        lambda: [
            SimpleNamespace(
                slug="collection.info",
                name="Collection Info",
                description="Inspect collection",
                domains=["collection.table"],
                to_mcp_descriptor=lambda: {
                    "description": "Inspect collection",
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "object"},
                },
            )
        ],
    )

    tools = await resolver.load_discovered_tools(instance=instance, provider=provider)

    assert [tool.slug for tool in tools] == ["collection.search", "collection.info"]


@pytest.mark.asyncio
async def test_load_discovered_tools_adds_builtin_collection_info_for_mcp_backed_api_collection(monkeypatch):
    resolver = CollectionToolResolver(session=SimpleNamespace())
    instance = SimpleNamespace(id="data-1", is_data=True, config={}, domain="collection.api")
    provider = SimpleNamespace(
        id="provider-1",
        slug="netbox-mcp",
        instance_kind="service",
        config={"provider_kind": "mcp"},
        connector_type="mcp",
        placement="remote",
    )
    resolver._resolve_bound_collection = AsyncMock(
        return_value=SimpleNamespace(id="collection-1", collection_type="api", has_vector_search=False)
    )
    resolver._load_local_tools_for_provider = AsyncMock(return_value=[])
    resolver._load_provider_tools = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.services.collection_tool_resolver.ToolRegistry.list_all",
        lambda: [
            SimpleNamespace(
                slug="collection.info",
                name="Collection Info",
                description="Inspect collection",
                domains=["collection.api"],
                to_mcp_descriptor=lambda: {
                    "description": "Inspect collection",
                    "inputSchema": {"type": "object"},
                    "outputSchema": {"type": "object"},
                },
            )
        ],
    )

    tools = await resolver.load_discovered_tools(instance=instance, provider=provider)

    assert [tool.slug for tool in tools] == ["collection.info"]


@pytest.mark.asyncio
async def test_load_system_tools_skips_stale_non_system_template_handlers(monkeypatch):
    resolver = CollectionToolResolver(session=SimpleNamespace())
    execute_result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(
            all=lambda: [
                SimpleNamespace(slug="collection.template.fill", domains=["system"]),
                SimpleNamespace(slug="file.read", domains=["system"]),
            ]
        )
    )
    resolver.session.execute = AsyncMock(return_value=execute_result)

    monkeypatch.setattr(
        "app.services.collection_tool_resolver.ToolRegistry.get",
        lambda slug: SimpleNamespace(domains=["collection.template"]) if slug == "collection.template.fill" else SimpleNamespace(domains=["system"]),
    )

    tools = await resolver._load_system_tools()  # noqa: SLF001

    assert [tool.slug for tool in tools] == ["file.read"]


@pytest.mark.asyncio
async def test_resolve_bound_collection_for_service_backed_local_collection(monkeypatch):
    resolver = CollectionToolResolver(session=SimpleNamespace())
    instance = SimpleNamespace(id="svc-1", is_data=False, instance_kind="service")
    bound = SimpleNamespace(id="collection-1", slug="reglament", collection_type="document")

    mocked = AsyncMock(return_value=bound)
    monkeypatch.setattr(
        "app.services.collection_tool_resolver.resolve_bound_collection_by_instance_id",
        mocked,
    )

    result = await resolver._resolve_bound_collection(instance)  # noqa: SLF001

    assert result is bound
    mocked.assert_awaited_once_with(resolver.session, data_instance_id="svc-1")
