from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.params import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.api.v1.routers.collections.stream import (
    redis_dependency as collection_redis_dependency,
    retry_collection_ingest,
    start_collection_ingest,
    stop_collection_ingest,
)
from app.api.v1.routers.rag.stream import retry_ingest, start_ingest, stop_ingest
from app.core.security import UserCtx
from app.main import app


@pytest.mark.parametrize(
    ("endpoint", "name"),
    [
        (start_collection_ingest, "collections.start"),
        (stop_collection_ingest, "collections.stop"),
        (retry_collection_ingest, "collections.retry"),
        (start_ingest, "rag.start"),
        (stop_ingest, "rag.stop"),
        (retry_ingest, "rag.retry"),
    ],
)
def test_mutating_ingest_routes_use_db_uow(endpoint, name):
    session_default = inspect.signature(endpoint).parameters["session"].default
    assert isinstance(session_default, Depends), name
    assert session_default.dependency is db_uow, name


@pytest.mark.asyncio
async def test_collection_start_ingest_commits_via_db_uow():
    tenant_id = uuid.uuid4()
    collection_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    user = UserCtx(id=str(uuid.uuid4()), email="admin@example.com", role="admin", tenant_ids=[str(tenant_id)])

    session = AsyncMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()

    async def fake_get_db():
        yield session

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[collection_redis_dependency] = lambda: object()

    try:
        with patch("app.api.deps.get_db", fake_get_db):
            with patch(
                "app.api.v1.routers.collections.stream._resolve_collection_and_doc",
                AsyncMock(
                    return_value=(
                        SimpleNamespace(id=collection_id, tenant_id=tenant_id, collection_type="document"),
                        SimpleNamespace(id=doc_id, tenant_id=tenant_id),
                        doc_id,
                        object(),
                    )
                ),
            ):
                with patch(
                    "app.api.v1.routers.collections.stream._ensure_worker_ready",
                    AsyncMock(),
                ):
                    with patch("app.services.rag_event_publisher.RAGEventPublisher") as mock_event_publisher_cls:
                        event_publisher = SimpleNamespace(
                            publish_ingest_started=AsyncMock()
                        )
                        mock_event_publisher_cls.return_value = event_publisher

                        with patch("app.services.rag_status_manager.RAGStatusManager") as mock_status_manager_cls:
                            status_manager = SimpleNamespace(
                                get_ingest_policy=AsyncMock(
                                    return_value={
                                        "start_allowed": True,
                                        "start_reason": None,
                                        "active_stages": [],
                                        "controls": [],
                                    }
                                ),
                                start_ingest=AsyncMock(),
                                dispatch_ingest_pipeline=AsyncMock(
                                    return_value=["embed.local.minilm"]
                                ),
                            )
                            mock_status_manager_cls.return_value = status_manager

                            async with AsyncClient(
                                transport=ASGITransport(app=app),
                                base_url="http://test",
                            ) as client:
                                response = await client.post(
                                    f"/api/v1/collections/{collection_id}/docs/{doc_id}/ingest/start"
                                )

        assert response.status_code == 200, response.text
        session.commit.assert_awaited_once()
        status_manager.start_ingest.assert_awaited_once_with(doc_id)
        status_manager.dispatch_ingest_pipeline.assert_awaited_once_with(doc_id, tenant_id)
        event_publisher.publish_ingest_started.assert_awaited_once()
    finally:
        app.dependency_overrides.clear()
