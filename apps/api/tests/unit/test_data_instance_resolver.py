from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.data_instance_resolver import CollectionRuntimeResolver


@pytest.mark.asyncio
async def test_resolver_keeps_service_backed_collection_chain():
    session = SimpleNamespace()
    instance_service = SimpleNamespace(
        evaluate_instance_readiness=AsyncMock(return_value=(True, "ready", None))
    )
    resolver = CollectionRuntimeResolver(session=session, instance_service=instance_service)

    collection = SimpleNamespace(collection_type="document", is_active=True)
    service_instance = SimpleNamespace(
        id="svc-1",
        slug="local-document-tools",
        is_data=False,
        is_active=True,
        health_status="healthy",
        access_via_instance_id=None,
        domain="collection.document",
    )

    resolver._load_active_collections = AsyncMock(return_value=[collection])  # noqa: SLF001
    resolver._resolve_collection_source = AsyncMock(return_value=service_instance)  # noqa: SLF001

    items = await resolver.resolve()

    assert len(items) == 1
    item = items[0]
    assert item.collection is collection
    assert item.instance is service_instance
    assert item.provider is service_instance
    assert item.readiness_reason == "ready"
    assert item.runtime_domain == "collection.document"


@pytest.mark.asyncio
async def test_resolver_uses_access_via_provider_for_remote_data():
    session = SimpleNamespace()
    instance_service = SimpleNamespace(
        evaluate_instance_readiness=AsyncMock(return_value=(True, "ready", None))
    )
    resolver = CollectionRuntimeResolver(session=session, instance_service=instance_service)

    collection = SimpleNamespace(collection_type="api", is_active=True)
    data_instance = SimpleNamespace(
        id="data-1",
        slug="netbox",
        is_data=True,
        access_via_instance_id="provider-1",
        domain="collection.api",
    )
    provider_instance = SimpleNamespace(
        id="provider-1",
        slug="mcp_netbox",
        is_data=False,
        is_active=True,
        health_status="healthy",
    )

    resolver._load_active_collections = AsyncMock(return_value=[collection])  # noqa: SLF001
    resolver._resolve_collection_source = AsyncMock(return_value=data_instance)  # noqa: SLF001
    resolver._resolve_provider_instance = AsyncMock(return_value=provider_instance)  # noqa: SLF001

    items = await resolver.resolve()

    assert len(items) == 1
    item = items[0]
    assert item.instance is data_instance
    assert item.provider is provider_instance
    assert item.collection is collection
    assert item.readiness_reason == "ready"
    assert item.runtime_domain == "collection.api"


@pytest.mark.asyncio
async def test_local_collection_type_selects_provider_without_reading_legacy_binding():
    local_template_service = SimpleNamespace(slug="local-template-tools")
    instance_service = SimpleNamespace(
        resolve_local_service_for_collection_type=AsyncMock(
            return_value=local_template_service
        )
    )
    resolver = CollectionRuntimeResolver(session=SimpleNamespace(), instance_service=instance_service)
    collection = SimpleNamespace(
        collection_type="template",
        data_instance=SimpleNamespace(slug="legacy-template-data"),
    )

    source = await resolver._resolve_collection_source(collection)  # noqa: SLF001

    assert source is local_template_service
    instance_service.resolve_local_service_for_collection_type.assert_awaited_once_with("template")
