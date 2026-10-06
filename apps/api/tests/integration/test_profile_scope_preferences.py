"""Exercise HTTP principal and validation boundaries without a database service."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import db_uow, get_current_user
from app.api.v1.routers import profile
from app.models.user import Users


@pytest.mark.asyncio
async def test_personal_scope_endpoint_updates_only_the_authenticated_user(monkeypatch):
    from app.services import memory_scope_preferences_service as module

    actor_id = uuid4()
    user = SimpleNamespace(lifecycle_status='active', memory_scope_keys=[])
    session = SimpleNamespace(get=AsyncMock(return_value=user), flush=AsyncMock(), commit=AsyncMock())
    monkeypatch.setattr(module, 'resolve_memory_scopes', AsyncMock(return_value=[
        SimpleNamespace(key='team.ops', scope_type='team', is_all=False),
    ]))
    app = FastAPI()
    app.include_router(profile.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=str(actor_id))
    app.dependency_overrides[db_uow] = lambda: session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        result = await client.put('/profile/memory-scopes', json={'memory_scope_keys': [' Team.Ops ']})
        assert result.status_code == 200
        assert result.json() == {'memory_scope_keys': ['team.ops']}
        session.get.assert_awaited_once_with(Users, actor_id)
        assert user.memory_scope_keys == ['team.ops']
        forged = await client.put('/profile/memory-scopes', json={'memory_scope_keys': [], 'user_id': str(uuid4())})
        assert forged.status_code == 422
        assert session.get.await_count == 1
        invalid = await client.put('/profile/memory-scopes', json={'memory_scope_keys': None})
        assert invalid.status_code == 422
        assert user.memory_scope_keys == ['team.ops']


@pytest.mark.asyncio
async def test_personal_scope_endpoint_rejects_non_catalog_keys_without_mutation(monkeypatch):
    from app.services import memory_scope_preferences_service as module

    session = SimpleNamespace(get=AsyncMock(), flush=AsyncMock())
    monkeypatch.setattr(module, 'resolve_memory_scopes', AsyncMock(side_effect=ValueError('Unknown memory scope: user')))
    app = FastAPI()
    app.include_router(profile.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=str(uuid4()))
    app.dependency_overrides[db_uow] = lambda: session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        result = await client.put('/profile/memory-scopes', json={'memory_scope_keys': ['user']})
    assert result.status_code == 422
    session.get.assert_not_awaited()
    session.flush.assert_not_awaited()
