from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.repositories.credential_set_repository import CredentialRepository


@pytest.mark.asyncio
async def test_platform_first_prefers_platform():
    repo = CredentialRepository(session=SimpleNamespace())
    platform_cred = SimpleNamespace(id=uuid4(), owner_platform=True)
    tenant_cred = SimpleNamespace(id=uuid4(), owner_tenant_id=uuid4())
    user_cred = SimpleNamespace(id=uuid4(), owner_user_id=uuid4())

    repo._find_platform = AsyncMock(return_value=platform_cred)  # type: ignore[method-assign]
    repo._find_tenant = AsyncMock(return_value=tenant_cred)  # type: ignore[method-assign]
    repo._find_user = AsyncMock(return_value=user_cred)  # type: ignore[method-assign]

    resolved = await repo.resolve_for_instance(
        instance_id=uuid4(),
        strategy="PLATFORM_FIRST",
        user_id=uuid4(),
        tenant_id=uuid4(),
    )

    assert resolved is platform_cred
    repo._find_platform.assert_awaited_once()  # type: ignore[attr-defined]
    repo._find_tenant.assert_not_awaited()  # type: ignore[attr-defined]
    repo._find_user.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_platform_first_falls_back_to_tenant_then_user():
    repo = CredentialRepository(session=SimpleNamespace())
    tenant_cred = SimpleNamespace(id=uuid4(), owner_tenant_id=uuid4())
    user_cred = SimpleNamespace(id=uuid4(), owner_user_id=uuid4())

    repo._find_platform = AsyncMock(return_value=None)  # type: ignore[method-assign]
    repo._find_tenant = AsyncMock(return_value=tenant_cred)  # type: ignore[method-assign]
    repo._find_user = AsyncMock(return_value=user_cred)  # type: ignore[method-assign]

    resolved = await repo.resolve_for_instance(
        instance_id=uuid4(),
        strategy="PLATFORM_FIRST",
        user_id=uuid4(),
        tenant_id=uuid4(),
    )

    assert resolved is tenant_cred
    repo._find_platform.assert_awaited_once()  # type: ignore[attr-defined]
    repo._find_tenant.assert_awaited_once()  # type: ignore[attr-defined]
    repo._find_user.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_platform_first_finally_uses_user():
    repo = CredentialRepository(session=SimpleNamespace())
    user_cred = SimpleNamespace(id=uuid4(), owner_user_id=uuid4())

    repo._find_platform = AsyncMock(return_value=None)  # type: ignore[method-assign]
    repo._find_tenant = AsyncMock(return_value=None)  # type: ignore[method-assign]
    repo._find_user = AsyncMock(return_value=user_cred)  # type: ignore[method-assign]

    resolved = await repo.resolve_for_instance(
        instance_id=uuid4(),
        strategy="PLATFORM_FIRST",
        user_id=uuid4(),
        tenant_id=uuid4(),
    )

    assert resolved is user_cred
    repo._find_platform.assert_awaited_once()  # type: ignore[attr-defined]
    repo._find_tenant.assert_awaited_once()  # type: ignore[attr-defined]
    repo._find_user.assert_awaited_once()  # type: ignore[attr-defined]
