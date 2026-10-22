from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import db_session, require_admin
from app.api.v1.routers.admin import agents as agents_router


def _agent_response():
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(), slug="test-agent", agent_type="regular", name="Test Agent",
        description=None, tags=[], current_version_id=None, logging_level="brief",
        model="llm.test", temperature=0.35, requires_confirmation_for_write=True,
        risk_level="high", allow_all_collections=False, allowed_collection_ids=[],
        provides_keys=[], lifecycle_status="active", deprecated_at=None,
        retention_days=14, created_at=now, updated_at=now, versions=[],
    )


def _app(db):
    app = FastAPI()
    app.include_router(agents_router.router, prefix="/admin/agents")
    app.dependency_overrides[db_session] = lambda: db
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(role="admin")
    return app


@pytest.mark.asyncio
async def test_create_agent_forwards_execution_fields_and_commits(monkeypatch):
    calls = []

    class Service:
        def __init__(self, _db):
            pass

        async def create_agent(self, **kwargs):
            calls.append(kwargs)
            return _agent_response()

    monkeypatch.setattr(agents_router, "AgentService", Service)
    db = SimpleNamespace(commit=AsyncMock())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(db)), base_url="http://test"
    ) as client:
        response = await client.post("/admin/agents", json={
            "slug": "test-agent", "name": "Test Agent", "model": "llm.test",
            "temperature": 0.35, "requires_confirmation_for_write": True,
            "risk_level": "high",
        })

    assert response.status_code == 201
    assert calls[0]["temperature"] == 0.35
    assert calls[0]["requires_confirmation_for_write"] is True
    assert calls[0]["risk_level"] == "high"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_agent_list_response_includes_execution_settings():
    agent = _agent_response()

    class Scalars:
        def all(self):
            return [agent]

    db = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: Scalars())))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app(db)), base_url="http://test"
    ) as client:
        response = await client.get("/admin/agents")

    assert response.status_code == 200
    item = response.json()[0]
    assert item["model"] == "llm.test"
    assert item["temperature"] == 0.35
    assert item["requires_confirmation_for_write"] is True
    assert item["risk_level"] == "high"
