"""HTTP contract tests for the admin user endpoints."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import db_session, db_uow, require_admin
from app.api.v1.routers.admin import users as users_router


def _user(**overrides):
    now = datetime.now(timezone.utc)
    values = {
        "id": uuid4(),
        "login": "local-user",
        "email": None,
        "full_name": None,
        "role": "reader",
        "is_active": True,
        "auth_provider": "local",
        "deactivated_reason": None,
        "memory_scope_keys": ["ops"],
        "lifecycle_status": "active",
        "deprecated_at": None,
        "retention_days": None,
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }
    return SimpleNamespace(**(values | overrides))


@pytest.mark.asyncio
async def test_create_user_http_contract_uses_one_tenant_and_returns_scope_keys(monkeypatch):
    tenant_id = uuid4()
    created = _user()
    service_call = {}

    class Repo:
        def __init__(self, _session):
            pass

        async def get_default_tenant(self, _user_id):
            return tenant_id

    class Service:
        def __init__(self, _repo):
            pass

        async def create_user(self, **kwargs):
            service_call.update(kwargs)
            return created

    monkeypatch.setattr(users_router, "AsyncUsersRepository", Repo)
    monkeypatch.setattr(users_router, "AsyncUsersService", Service)
    app = FastAPI()
    app.include_router(users_router.router, prefix="/admin/users")
    app.dependency_overrides[db_uow] = lambda: object()
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(role="admin")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/admin/users", json={
            "login": "local-user",
            "password": "a-secure-password",
            "tenant_id": str(tenant_id),
            "memory_scope_keys": ["ops"],
        })
        legacy = await client.post("/admin/users", json={
            "login": "legacy-user",
            "password": "a-secure-password",
            "tenant_ids": [str(tenant_id)],
        })

    assert response.status_code == 200
    assert response.json()["tenant_id"] == str(tenant_id)
    assert response.json()["memory_scope_keys"] == ["ops"]
    assert service_call["tenant_id"] == tenant_id
    assert service_call["memory_scope_keys"] == ["ops"]
    assert legacy.status_code == 422


@pytest.mark.asyncio
async def test_patch_user_http_contract_preserves_explicit_tenant_clear(monkeypatch):
    user_id = uuid4()
    current = _user(id=user_id)
    update_call = {}

    class Repo:
        def __init__(self, _session):
            pass

        async def get_by_id(self, _user_id):
            return current

        async def get_default_tenant(self, _user_id):
            return None

    class Service:
        def __init__(self, _repo):
            pass

        async def update_user(self, _user_id, updates):
            update_call.update(updates)
            return current

    monkeypatch.setattr(users_router, "AsyncUsersRepository", Repo)
    monkeypatch.setattr(users_router, "AsyncUsersService", Service)
    app = FastAPI()
    app.include_router(users_router.router, prefix="/admin/users")
    app.dependency_overrides[db_uow] = lambda: object()
    app.dependency_overrides[db_session] = lambda: object()
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(role="admin")

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(f"/admin/users/{user_id}", json={
            "tenant_id": None,
            "memory_scope_keys": [],
        })

    assert response.status_code == 200
    assert response.json()["tenant_id"] is None
    assert update_call == {"tenant_id": None, "memory_scope_keys": []}
