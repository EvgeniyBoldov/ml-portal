from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.routers.profile import _managed_tenant
from app.api.deps import require_admin
from app.core.security import UserCtx


@pytest.mark.asyncio
async def test_tenant_admin_can_manage_their_tenant():
    tenant_id = uuid4()
    session = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(is_tenant_admin=True)))
    user = UserCtx(id=str(uuid4()), tenant_ids=[str(tenant_id)])

    assert await _managed_tenant(session, user) == tenant_id


@pytest.mark.asyncio
async def test_regular_member_cannot_manage_tenant():
    tenant_id = uuid4()
    session = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(is_tenant_admin=False)))
    user = UserCtx(id=str(uuid4()), tenant_ids=[str(tenant_id)])

    with pytest.raises(HTTPException) as error:
        await _managed_tenant(session, user)

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_user_without_tenant_cannot_manage_tenant():
    session = SimpleNamespace(scalar=AsyncMock())
    user = UserCtx(id=str(uuid4()), tenant_ids=[])

    with pytest.raises(HTTPException) as error:
        await _managed_tenant(session, user)

    assert error.value.status_code == 403
    session.scalar.assert_not_awaited()


def test_platform_admin_flag_controls_admin_application_access():
    platform_admin = UserCtx(id=str(uuid4()), role="reader", is_admin=True)
    tenant_admin = UserCtx(id=str(uuid4()), role="reader", tenant_admin_ids=[str(uuid4())])

    assert require_admin(platform_admin) is platform_admin
    with pytest.raises(HTTPException) as error:
        require_admin(tenant_admin)
    assert error.value.status_code == 403
