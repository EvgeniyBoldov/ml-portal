from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.credential_service import CredentialService


def _credential(*, instance_id, owner_user_id=None, owner_tenant_id=None, owner_platform=False, age=0):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        instance_id=instance_id,
        owner_user_id=owner_user_id,
        owner_tenant_id=owner_tenant_id,
        owner_platform=owner_platform,
        is_active=True,
        updated_at=now - timedelta(seconds=age),
        created_at=now - timedelta(seconds=age),
    )


@pytest.mark.asyncio
async def test_deduplicate_active_credentials_keeps_newest_per_owner_scope() -> None:
    instance_id = uuid4()
    user_id = uuid4()
    tenant_id = uuid4()
    newest_user = _credential(instance_id=instance_id, owner_user_id=user_id, age=0)
    older_user = _credential(instance_id=instance_id, owner_user_id=user_id, age=10)
    tenant_credential = _credential(instance_id=instance_id, owner_tenant_id=tenant_id, age=0)

    service = CredentialService.__new__(CredentialService)
    service.session = SimpleNamespace(flush=AsyncMock())
    service.repo = SimpleNamespace(
        lock_all_active=AsyncMock(return_value=[newest_user, older_user, tenant_credential]),
    )

    report = await service.deduplicate_active_credentials(instance_id=instance_id)

    assert newest_user.is_active is True
    assert older_user.is_active is False
    assert tenant_credential.is_active is True
    assert report.groups_deduplicated == 1
    assert report.deactivated_credential_ids == [older_user.id]
    service.session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_deduplicate_active_credentials_is_noop_without_duplicates() -> None:
    instance_id = uuid4()
    credential = _credential(instance_id=instance_id, owner_platform=True)
    service = CredentialService.__new__(CredentialService)
    service.session = SimpleNamespace(flush=AsyncMock())
    service.repo = SimpleNamespace(lock_all_active=AsyncMock(return_value=[credential]))

    report = await service.deduplicate_active_credentials(instance_id=instance_id)

    assert report.groups_deduplicated == 0
    assert report.deactivated_credential_ids == []
    service.session.flush.assert_not_awaited()
