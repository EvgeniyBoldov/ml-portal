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
        is_active=False,
    )
    dependent = SimpleNamespace(
        lifecycle_status="deprecated",
        deprecated_at=object(),
        deprecated_by=object(),
        deprecated_reason="test",
        is_active=False,
    )

    async def get_entity(kind, entity_id):  # type: ignore[no-untyped-def]
        if entity_id == root_id:
            return root
        if entity_id == dependent_id:
            return dependent
        return None

    svc._get_entity = AsyncMock(side_effect=get_entity)  # type: ignore[attr-defined]
    svc.get_dependencies = AsyncMock(
        return_value=[
            {
                "resource_type": "users",
                "entities": [
                    {"uuid": str(dependent_id), "name": "User", "url": None},
                ],
            }
        ]
    )  # type: ignore[attr-defined]

    report = await svc.restore("tenant", root_id)

    assert report.lifecycle_status == "active"
    assert report.restored == {"tenants": 1, "users": 1}
    assert root.lifecycle_status == "active"
    assert root.is_active is True
    assert dependent.lifecycle_status == "active"
    assert dependent.is_active is True
