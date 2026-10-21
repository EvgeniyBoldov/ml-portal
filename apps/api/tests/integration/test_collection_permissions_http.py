"""HTTP permission boundary with stubbed persistence; no external services."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import db_uow, get_current_user
from app.api.v1.routers.collections import crud, table, upload_shared
from app.services.permission_service import EffectivePermissions


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "DELETE"])
@pytest.mark.parametrize("allowed", [False, True])
async def test_effective_policy_protects_direct_data_routes(monkeypatch, method, allowed):
    tenant_id = uuid4()
    collection = SimpleNamespace(slug="private", tenant_id=tenant_id, collection_type="table")
    service = SimpleNamespace(get_by_slug=AsyncMock(return_value=collection),
                              search=AsyncMock(return_value=[]), count=AsyncMock(return_value=0),
                              delete_rows=AsyncMock(return_value=1))
    monkeypatch.setattr(upload_shared, "CollectionService", lambda session: service)
    monkeypatch.setattr(upload_shared, "_resolve_requested_tenant_id", AsyncMock(return_value=tenant_id))
    monkeypatch.setattr(crud, "_resolve_collection_permissions", AsyncMock(return_value=EffectivePermissions(
        collection_permissions={"private": allowed}, default_collection_allow=not allowed)))
    app = FastAPI()
    app.include_router(table.router, prefix="/collections")
    session = AsyncMock()
    user = SimpleNamespace(id=str(uuid4()), tenant_ids=[str(tenant_id)], role="user")
    app.dependency_overrides[db_uow] = lambda: session
    app.dependency_overrides[get_current_user] = lambda: user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(method, f"/collections/private/data?ids={uuid4()}")
    assert response.status_code == (200 if allowed else 404)
    if not allowed:
        service.search.assert_not_awaited()
        service.delete_rows.assert_not_awaited()
        session.commit.assert_not_awaited()
    elif method == "GET":
        assert response.json()["total"] == 0
        service.search.assert_awaited_once()
    else:
        assert response.json()["deleted"] == 1
        service.delete_rows.assert_awaited_once()
        session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_document_stream_checks_document_membership_before_subscribing(monkeypatch):
    from fastapi import HTTPException
    from app.api.deps import db_session, get_current_user_sse
    from app.api.v1.routers.collections import stream_events

    membership = AsyncMock(side_effect=HTTPException(404, "Document not found in collection"))
    monkeypatch.setattr(stream_events, "_resolve_collection_and_doc", membership)
    monkeypatch.setattr(stream_events, "_resolve_document_collection", AsyncMock(side_effect=AssertionError("Document membership must be checked")))
    monkeypatch.setattr(stream_events, "get_settings", lambda: SimpleNamespace(REDIS_URL="redis://unused"))
    app = FastAPI()
    app.include_router(stream_events.router, prefix="/collections")
    app.dependency_overrides[db_session] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user_sse] = lambda: SimpleNamespace(id=str(uuid4()), tenant_ids=[], role="user")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/collections/{uuid4()}/docs/{uuid4()}/status/events")
    assert response.status_code == 404
    membership.assert_awaited_once()
