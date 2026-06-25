from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.lifecycle_admin_service import LifecycleAdminService


@pytest.mark.asyncio
async def test_soft_delete_tenant_blocks_platform_default():
    session = AsyncMock()
    svc = LifecycleAdminService(session)

    tenant = SimpleNamespace(is_platform_default=True)
    svc._get_entity = AsyncMock(return_value=tenant)  # type: ignore[attr-defined]

    with pytest.raises(ValueError) as exc_info:
        await svc.soft_delete(
            "tenant",
            uuid4(),
            actor_id=None,
            reason=None,
            retention_days=None,
        )

    assert str(exc_info.value) == "cannot_delete_default_tenant"


@pytest.mark.asyncio
async def test_soft_delete_user_marks_deprecated_and_inactive():
    session = AsyncMock()
    svc = LifecycleAdminService(session)

    user = SimpleNamespace(
        lifecycle_status="active",
        deprecated_at=None,
        deprecated_by=None,
        deprecated_reason=None,
        retention_days=14,
        is_active=True,
    )
    svc._get_entity = AsyncMock(return_value=user)  # type: ignore[attr-defined]

    report = await svc.soft_delete(
        "user",
        uuid4(),
        actor_id=None,
        reason="test",
        retention_days=7,
    )

    assert report.lifecycle_status == "deprecated"
    assert user.lifecycle_status == "deprecated"
    assert user.is_active is False
    assert user.retention_days == 7


@pytest.mark.asyncio
async def test_soft_delete_cascade_marks_dependencies_with_root_provenance():
    session = AsyncMock()
    svc = LifecycleAdminService(session)

    root_id = uuid4()
    dependent_id = uuid4()
    tenant = SimpleNamespace(
        lifecycle_status="active",
        deprecated_at=None,
        deprecated_by=None,
        deprecated_reason=None,
        retention_days=14,
        delete_cascade=False,
        deprecated_root_kind=None,
        deprecated_root_id=None,
        is_platform_default=False,
        is_active=True,
    )
    user = SimpleNamespace(
        lifecycle_status="active",
        deprecated_at=None,
        deprecated_by=None,
        deprecated_reason=None,
        retention_days=14,
        delete_cascade=False,
        deprecated_root_kind=None,
        deprecated_root_id=None,
        is_active=True,
    )

    async def get_entity(kind, entity_id):  # type: ignore[no-untyped-def]
        if kind == "tenant" and entity_id == root_id:
            return tenant
        if kind == "user" and entity_id == dependent_id:
            return user
        return None

    svc._get_entity = AsyncMock(side_effect=get_entity)  # type: ignore[attr-defined]
    svc.get_dependencies = AsyncMock(  # type: ignore[attr-defined]
        return_value=[
            {
                "resource_type": "users",
                "entities": [{"uuid": str(dependent_id), "name": "User", "url": None}],
            }
        ]
    )

    report = await svc.soft_delete(
        "tenant",
        root_id,
        actor_id=None,
        reason="cascade",
        retention_days=9,
        cascade=True,
    )

    assert report.lifecycle_status == "deprecated"
    assert report.cascaded == {"users": 1}
    assert tenant.lifecycle_status == "deprecated"
    assert tenant.delete_cascade is True
    assert tenant.deprecated_root_kind == "tenant"
    assert tenant.deprecated_root_id == root_id
    assert user.lifecycle_status == "deprecated"
    assert user.delete_cascade is True
    assert user.deprecated_root_kind == "tenant"
    assert user.deprecated_root_id == root_id


@pytest.mark.asyncio
async def test_restore_restores_entity_and_deprecated_dependencies():
    session = AsyncMock()
    svc = LifecycleAdminService(session)

    root_id = uuid4()
    dependent_id = uuid4()
    root = SimpleNamespace(
        lifecycle_status="deprecated",
        deprecated_at=object(),
        deprecated_by=object(),
        deprecated_reason="test",
        delete_cascade=True,
        deprecated_root_kind="tenant",
        deprecated_root_id=root_id,
        is_active=False,
    )
    dependent = SimpleNamespace(
        lifecycle_status="deprecated",
        deprecated_at=object(),
        deprecated_by=object(),
        deprecated_reason="test",
        delete_cascade=True,
        deprecated_root_kind="tenant",
        deprecated_root_id=root_id,
        is_active=False,
    )

    async def get_entity(kind, entity_id):  # type: ignore[no-untyped-def]
        if entity_id == root_id:
            return root
        if entity_id == dependent_id:
            return dependent
        return None

    svc._get_entity = AsyncMock(side_effect=get_entity)  # type: ignore[attr-defined]
    svc._find_cascaded_entity_ids = AsyncMock(  # type: ignore[attr-defined]
        side_effect=lambda kind, root_kind, root_id: [dependent_id] if kind == "user" else []
    )

    report = await svc.restore("tenant", root_id)

    assert report.lifecycle_status == "active"
    assert report.restored == {"tenants": 1, "users": 1}
    assert root.lifecycle_status == "active"
    assert root.is_active is True
    assert root.delete_cascade is False
    assert root.deprecated_root_kind is None
    assert root.deprecated_root_id is None
    assert dependent.lifecycle_status == "active"
    assert dependent.is_active is True
    assert dependent.delete_cascade is False
    assert dependent.deprecated_root_kind is None
    assert dependent.deprecated_root_id is None
