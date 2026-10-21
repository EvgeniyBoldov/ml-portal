from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import db_uow, get_current_user
from app.api.v1.routers import memory_scopes


@pytest.mark.asyncio
async def test_scope_catalog_is_available_without_a_legacy_collection_or_tenant(monkeypatch):
    scope_id = uuid4()
    catalog = AsyncMock(return_value=[SimpleNamespace(
        id=scope_id, key="company", name="Компания", aliases=[], scope_type="project", is_all=False)])
    monkeypatch.setattr(memory_scopes, "list_memory_scopes", catalog)
    session = AsyncMock()
    app = FastAPI()
    app.include_router(memory_scopes.router)
    app.dependency_overrides[db_uow] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=str(uuid4()), tenant_ids=[])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/memory/scopes")
    assert response.status_code == 200
    assert response.json() == [{"id": str(scope_id), "key": "company", "name": "Компания",
                                "aliases": [], "scope_type": "project", "is_all": False}]
    catalog.assert_awaited_once_with(session)
