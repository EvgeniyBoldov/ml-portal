from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api import deps
from app.api.v1.routers.collections import crud as collections_crud
from app.core.security import UserCtx


class _RowsResult:
    def __init__(self, rows: list[tuple[object]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object]]:
        return self._rows


class _ScalarResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


@pytest.mark.asyncio
async def test_collection_scope_uses_db_default_not_stale_jwt_order() -> None:
    default_tenant = uuid4()
    stale_jwt_tenant = uuid4()
    user = UserCtx(id=str(uuid4()), tenant_ids=[str(stale_jwt_tenant), str(default_tenant)])
    session = AsyncMock()
    session.execute.return_value = _RowsResult([(default_tenant,), (stale_jwt_tenant,)])

    tenant_ids = await collections_crud._resolve_user_tenants(session, user)

    assert tenant_ids == [default_tenant, stale_jwt_tenant]
    assert user.tenant_ids == [str(default_tenant), str(stale_jwt_tenant)]


@pytest.mark.asyncio
async def test_chat_scope_uses_db_default_not_stale_jwt_order() -> None:
    chat_id = uuid4()
    user_id = uuid4()
    default_tenant = uuid4()
    stale_jwt_tenant = uuid4()
    chat = SimpleNamespace(id=chat_id, owner_id=user_id, name="Normal chat")
    session = AsyncMock()
    session.execute.side_effect = [
        _ScalarResult(chat),
        _RowsResult([(default_tenant,), (stale_jwt_tenant,)]),
    ]
    user = UserCtx(id=str(user_id), tenant_ids=[str(stale_jwt_tenant), str(default_tenant)])

    context = await deps.resolve_chat_context(str(chat_id), session=session, current_user=user)

    assert context.tenant_id == str(default_tenant)
    assert user.tenant_ids == [str(default_tenant), str(stale_jwt_tenant)]
