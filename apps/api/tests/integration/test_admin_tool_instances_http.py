"""HTTP contract tests for the admin connector endpoints."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import db_session, require_admin
from app.api.v1.routers.admin import tool_instances as instances_router


def _instance(**overrides):
    now = datetime.now(timezone.utc)
    values = {
        "id": uuid4(),
        "slug": "inventory-api",
        "name": "Inventory API",
        "description": "Inventory service",
        "instance_kind": "data",
        "connector_type": "data",
        "connector_subtype": "api",
        "placement": "remote",
        "provider_kind": None,
        "url": "https://inventory.example.test",
        "config": {"base_path": "/v1"},
        "health_status": "healthy",
        "is_active": True,
        "access_via_instance_id": None,
        "created_at": now,
        "updated_at": now,
        "access_via": None,
    }
    return SimpleNamespace(**(values | overrides))


def _app():
    app = FastAPI()
    app.include_router(instances_router.router, prefix="/admin/connectors")
    app.dependency_overrides[db_session] = lambda: SimpleNamespace(
        commit=AsyncMock(), refresh=AsyncMock()
    )
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(role="admin")
    return app


@pytest.mark.asyncio
async def test_list_connectors_http_forwards_filters_and_returns_public_fields(monkeypatch):
    service_call = {}

    class Service:
        def __init__(self, _session):
            pass

        async def list_instances(self, **kwargs):
            service_call.update(kwargs)
            return [_instance()], 1

    monkeypatch.setattr(instances_router, "ToolInstanceService", Service)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app()), base_url="http://test") as client:
        response = await client.get(
            "/admin/connectors?skip=5&limit=25&is_active=true&connector_type=data&connector_subtype=api&placement=remote"
        )

    assert response.status_code == 200
    assert response.json()[0]["connector_subtype"] == "api"
    assert response.json()[0]["provider_kind"] is None
    assert service_call == {
        "skip": 5, "limit": 25, "is_active": True, "instance_kind": None,
        "connector_type": "data", "placement": "remote", "connector_subtype": "api",
    }


@pytest.mark.asyncio
async def test_create_connector_http_derives_slug_and_commits(monkeypatch):
    calls = {}
    session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

    class Service:
        def __init__(self, _session):
            pass

        async def create_instance(self, **kwargs):
            calls.update(kwargs)
            return _instance(slug=kwargs["slug"], name=kwargs["name"])

    monkeypatch.setattr(instances_router, "ToolInstanceService", Service)
    app = _app()
    app.dependency_overrides[db_session] = lambda: session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/admin/connectors", json={
            "name": "Inventory API", "connector_type": "data", "connector_subtype": "api",
            "url": "https://inventory.example.test", "config": {"base_path": "/v1"},
        })

    assert response.status_code == 201
    assert calls["slug"] == "inventory-api"
    assert calls["connector_subtype"] == "api"
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_connector_http_preserves_explicit_provider_link_clear(monkeypatch):
    instance_id = uuid4()
    calls = {}
    session = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

    class Service:
        def __init__(self, _session):
            pass

        async def update_instance(self, **kwargs):
            calls.update(kwargs)
            return _instance(id=instance_id, name="Updated")

    monkeypatch.setattr(instances_router, "ToolInstanceService", Service)
    app = _app()
    app.dependency_overrides[db_session] = lambda: session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(f"/admin/connectors/{instance_id}", json={
            "name": "Updated", "access_via_instance_id": None,
        })

    assert response.status_code == 200
    assert calls["instance_id"] == instance_id
    assert calls["access_via_instance_id"] is None
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_connector_create_requires_data_subtype_and_delete_is_no_content(monkeypatch):
    service = SimpleNamespace(delete_instance=AsyncMock())

    class Service:
        def __init__(self, _session):
            pass

        async def delete_instance(self, instance_id):
            await service.delete_instance(instance_id)

    monkeypatch.setattr(instances_router, "ToolInstanceService", Service)
    app = _app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        invalid = await client.post("/admin/connectors", json={
            "name": "Missing subtype", "connector_type": "data", "url": "https://example.test",
        })
        deleted = await client.delete(f"/admin/connectors/{uuid4()}")

    assert invalid.status_code == 422
    assert deleted.status_code == 204
    service.delete_instance.assert_awaited_once()
