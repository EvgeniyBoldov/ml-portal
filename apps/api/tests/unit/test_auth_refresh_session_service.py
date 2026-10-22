from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.services.auth_refresh_session_service import AuthRefreshSessionService


@pytest.mark.asyncio
async def test_rotate_consumes_old_session_and_issues_successor(monkeypatch):
    session = AsyncMock()
    old_row = SimpleNamespace(
        user_id=uuid4(),
        family_id=uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        consumed_at=None,
        revoked_at=None,
    )
    session.scalar.return_value = old_row
    service = AuthRefreshSessionService(session)
    service.issue = AsyncMock()

    rotated = await service.rotate(
        jti=uuid4(),
        family_id=old_row.family_id,
        user_id=old_row.user_id,
        next_jti=uuid4(),
        next_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    assert rotated is True
    assert old_row.consumed_at is not None
    service.issue.assert_awaited_once()


@pytest.mark.asyncio
async def test_replay_revokes_live_family_descendants():
    session = AsyncMock()
    old_row = SimpleNamespace(
        user_id=uuid4(), family_id=uuid4(), expires_at=datetime.now(timezone.utc),
        consumed_at=datetime.now(timezone.utc), revoked_at=None,
    )
    session.scalar.return_value = old_row
    service = AuthRefreshSessionService(session)

    rotated = await service.rotate(
        jti=uuid4(),
        family_id=old_row.family_id,
        user_id=old_row.user_id,
        next_jti=uuid4(),
        next_expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )

    assert rotated is False
    session.execute.assert_awaited_once()
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_family_is_active_only_with_unconsumed_unrevoked_session():
    session = AsyncMock()
    session.scalar.return_value = uuid4()
    service = AuthRefreshSessionService(session)

    assert await service.family_is_active(family_id=uuid4(), user_id=uuid4()) is True
    session.scalar.assert_awaited_once()
