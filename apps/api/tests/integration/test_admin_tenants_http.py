"""HTTP contract tests for admin tenant pagination and conflicts."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import db_uow, require_admin
from app.api.v1.routers.admin import tenants as tenants_router


def _tenant(**overrides):
    now = datetime.now(timezone.utc)
    values = {
        "id": str(uuid4()),
        "name": "Operations",
        "description": "Operational workspace",
        "is_active": True,
        "is_default": False,
        "memory_scope_keys": ["ops"],
        "embed_models": [],
        "rerank_model": None,
        "extra_embed_model": None,
        "ocr": False,
        "layout": False,
        "lifecycle_status": "active",
        "deprecated_at": None,
        "retention_days": 14,
        "created_at": now,
        "updated_at": now,
    }
    return values | overrides


def _app():
    app = FastAPI()
    app.include_router(tenants_router.router, prefix="/admin/tenants")
    app.dependency_overrides[db_uow] = lambda: object()
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(role="admin")
    return app


@pytest.mark.asyncio
async def test_list_tenants_http_uses_server_pagination_and_search(monkeypatch):
    service_call = {}

    class Service:
        def __init__(self, _session):
            pass

        async def list_tenants_page(self, **kwargs):
            service_call.update(kwargs)
            return [_tenant()], 201

    monkeypatch.setattr(tenants_router, "AsyncTenantsService", Service)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://test") as client:
        response = await client.get(
            "/admin/tenants?page=1&size=100&search=operations&is_active=true&include_deprecated=true"
        )

    assert response.status_code == 200
    assert response.json()["total"] == 201
    assert response.json()["has_more"] is True
    assert response.json()["items"][0]["memory_scope_keys"] == ["ops"]
    assert service_call == {
        "page": 1, "size": 100, "search": "operations", "is_active": True, "include_deprecated": True,
    }


@pytest.mark.asyncio
async def test_create_tenant_duplicate_name_is_a_conflict(monkeypatch):
    class Service:
        def __init__(self, _session):
            pass

        async def create_tenant(self, _data):
            raise ValueError("tenant_name_already_exists")

    monkeypatch.setattr(tenants_router, "AsyncTenantsService", Service)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://test") as client:
        response = await client.post("/admin/tenants", json={"name": "Operations"})

    assert response.status_code == 409
    assert response.json()["detail"] == "tenant_name_already_exists"


@pytest.mark.asyncio
async def test_direct_hard_delete_endpoint_is_removed():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://test") as client:
        response = await client.delete(f"/admin/tenants/{uuid4()}")

    assert response.status_code == 405
