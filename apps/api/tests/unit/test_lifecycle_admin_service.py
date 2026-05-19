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
