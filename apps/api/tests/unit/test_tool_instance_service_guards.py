from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.tool_instance import ToolInstance, InstanceKind, InstancePlacement
from app.services.tool_instance_service import (
    ToolInstanceService,
    ToolInstanceError,
    LocalInstanceProtectedError,
)


def _build_instance(
    *,
    placement: str = InstancePlacement.REMOTE.value,
    instance_kind: str = InstanceKind.DATA.value,
) -> ToolInstance:
    return ToolInstance(
        id=uuid4(),
        slug=f"inst-{uuid4().hex[:8]}",
        name="Instance",
        description=None,
        instance_kind=instance_kind,
        placement=placement,
        domain="jira" if instance_kind == InstanceKind.DATA.value else "mcp",
        url="https://example.org" if placement == InstancePlacement.REMOTE.value else "",
        config={},
        is_active=True,
    )


@pytest.mark.asyncio
async def test_create_remote_instance_requires_url():
    service = ToolInstanceService(session=MagicMock())
    service.repo.get_by_slug = AsyncMock(return_value=None)
    service.repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(ToolInstanceError, match="require non-empty url"):
        await service.create_instance(
            slug="jira-prod",
            name="Jira Prod",
            instance_kind=InstanceKind.DATA.value,
            placement=InstancePlacement.REMOTE.value,
            domain="jira",
            url="",
        )


@pytest.mark.asyncio
async def test_create_manual_local_instance_is_blocked():
    service = ToolInstanceService(session=MagicMock())
    service.repo.get_by_slug = AsyncMock(return_value=None)
    service.repo.get_by_id = AsyncMock(return_value=None)

    with pytest.raises(LocalInstanceProtectedError):
        await service.create_instance(
            slug="collection-tickets",
            name="Collection tickets",
            instance_kind=InstanceKind.DATA.value,
            placement=InstancePlacement.LOCAL.value,
            domain="collection.table",
            url="",
        )


@pytest.mark.asyncio
async def test_create_data_instance_validates_access_via_service():
    service = ToolInstanceService(session=MagicMock())
    service.repo.get_by_slug = AsyncMock(return_value=None)

    service_repo_target = _build_instance(
        placement=InstancePlacement.REMOTE.value,
        instance_kind=InstanceKind.SERVICE.value,
    )
    service.repo.get_by_id = AsyncMock(return_value=service_repo_target)
    service.repo.create = AsyncMock(side_effect=lambda instance: instance)

    created = await service.create_instance(
        slug="jira-prod",
        name="Jira Prod",
        instance_kind=InstanceKind.DATA.value,
        placement=InstancePlacement.REMOTE.value,
        domain="jira",
        url="https://jira.prod.local",
        access_via_instance_id=service_repo_target.id,
    )

    assert created.access_via_instance_id == service_repo_target.id


@pytest.mark.asyncio
async def test_update_local_instance_is_blocked():
    service = ToolInstanceService(session=MagicMock())
    local_instance = _build_instance(
        placement=InstancePlacement.LOCAL.value,
        instance_kind=InstanceKind.DATA.value,
    )
    service.get_instance = AsyncMock(return_value=local_instance)

    with pytest.raises(LocalInstanceProtectedError):
        await service.update_instance(local_instance.id, name="New Name")


@pytest.mark.asyncio
async def test_delete_local_instance_is_blocked():
    service = ToolInstanceService(session=MagicMock())
    local_instance = _build_instance(
        placement=InstancePlacement.LOCAL.value,
        instance_kind=InstanceKind.DATA.value,
    )
    service.get_instance = AsyncMock(return_value=local_instance)
    service.repo.delete = AsyncMock()

    with pytest.raises(LocalInstanceProtectedError):
        await service.delete_instance(local_instance.id)


@pytest.mark.asyncio
async def test_remote_data_instance_without_access_binding_is_not_ready():
    service = ToolInstanceService(session=MagicMock())
    instance = _build_instance(
        placement=InstancePlacement.REMOTE.value,
        instance_kind=InstanceKind.DATA.value,
    )
    instance.url = ""
    service._resolve_bound_collection = AsyncMock(return_value=None)

    ready, reason, semantic_source = await service.evaluate_instance_readiness(instance)

    assert ready is False
    assert reason == "missing_access_binding"
    assert semantic_source == "none"


@pytest.mark.asyncio
async def test_local_collection_instance_uses_derived_semantic_source():
    service = ToolInstanceService(session=MagicMock())
    instance = _build_instance(
        placement=InstancePlacement.LOCAL.value,
        instance_kind=InstanceKind.DATA.value,
    )
    instance.domain = "collection.table"
    instance.config = {"collection_id": str(uuid4())}
    service._resolve_bound_collection = AsyncMock(return_value=MagicMock())

    ready, reason, semantic_source = await service.evaluate_instance_readiness(instance)

    assert ready is True
    assert reason == "ready"
    assert semantic_source == "derived_collection"


@pytest.mark.asyncio
async def test_ensure_local_service_instances_create_when_missing():
    service = ToolInstanceService(session=MagicMock())
    service.repo.get_by_slug = AsyncMock(return_value=None)
    service.repo.create = AsyncMock(side_effect=lambda instance: instance)
    service.repo.update = AsyncMock(side_effect=lambda instance: instance)

    table_instance, document_instance, created, updated = await service.ensure_local_service_instances()

    assert created == 2
    assert updated == 0
    assert table_instance.slug == service.LOCAL_TABLE_SERVICE_SLUG
    assert document_instance.slug == service.LOCAL_DOCUMENT_SERVICE_SLUG
    assert table_instance.instance_kind == InstanceKind.SERVICE.value
    assert document_instance.instance_kind == InstanceKind.SERVICE.value
    assert table_instance.placement == InstancePlacement.LOCAL.value
    assert document_instance.placement == InstancePlacement.LOCAL.value
    assert table_instance.is_active is True
    assert document_instance.is_active is True


@pytest.mark.asyncio
async def test_ensure_local_service_instances_normalize_existing():
    service = ToolInstanceService(session=MagicMock())
    table_existing = _build_instance(
        placement=InstancePlacement.REMOTE.value,
        instance_kind=InstanceKind.DATA.value,
    )
    document_existing = _build_instance(
        placement=InstancePlacement.REMOTE.value,
        instance_kind=InstanceKind.DATA.value,
    )
    table_existing.slug = service.LOCAL_TABLE_SERVICE_SLUG
    table_existing.is_active = False
    table_existing.health_status = "unknown"
    table_existing.domain = "rag"
    document_existing.slug = service.LOCAL_DOCUMENT_SERVICE_SLUG
    document_existing.is_active = False
    document_existing.health_status = "unknown"
    document_existing.domain = "rag"
    service.repo.get_by_slug = AsyncMock(side_effect=[table_existing, document_existing])
    service.repo.update = AsyncMock(side_effect=lambda instance: instance)

    table_instance, document_instance, created, updated = await service.ensure_local_service_instances()

    assert created == 0
    assert updated == 2
    assert table_instance.instance_kind == InstanceKind.SERVICE.value
    assert document_instance.instance_kind == InstanceKind.SERVICE.value
    assert table_instance.placement == InstancePlacement.LOCAL.value
    assert document_instance.placement == InstancePlacement.LOCAL.value
    assert table_instance.domain == "collection.table"
    assert document_instance.domain == "collection.document"
    assert table_instance.is_active is True
    assert document_instance.is_active is True
    assert table_instance.health_status == "healthy"
    assert document_instance.health_status == "healthy"
