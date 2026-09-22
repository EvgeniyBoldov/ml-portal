from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.schemas.common import DocumentStatus
from app.schemas.rag import IngestProgress, IngestRequest
from app.services.rag_ingest_service import RAGIngestService


def _service() -> tuple[RAGIngestService, MagicMock]:
    session = MagicMock()
    factory = MagicMock(tenant_id=uuid4())
    status_manager = MagicMock()
    service = RAGIngestService(session, factory, status_manager)
    service.rag_repo = MagicMock()
    return service, status_manager


@pytest.mark.asyncio
async def test_start_ingest_uses_graph_policy_not_document_status() -> None:
    """A queued graph must not depend on a missing document enum member."""
    service, status_manager = _service()
    document_id = uuid4()
    service.rag_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(status="uploaded"))
    status_manager.get_ingest_policy = AsyncMock(return_value={"start_allowed": True})
    status_manager._get_target_models = AsyncMock(return_value=["default"])
    status_manager.start_ingest = AsyncMock()
    service._runs.create = AsyncMock(return_value=SimpleNamespace(id=uuid4()))
    service._commit_and_dispatch = AsyncMock(return_value="outbox-id")
    service._get_progress = AsyncMock(return_value=IngestProgress(
        document_id=document_id,
        current_step="extract",
        progress=0,
    ))

    response = await service.start_ingest(IngestRequest(document_id=document_id))

    assert response.status is DocumentStatus.PROCESSING
    status_manager.start_ingest.assert_awaited_once_with(document_id)


@pytest.mark.asyncio
async def test_start_ingest_returns_existing_graph_run_without_creating_another() -> None:
    service, status_manager = _service()
    document_id = uuid4()
    service.rag_repo.get_by_id = AsyncMock(return_value=SimpleNamespace(status="uploaded"))
    status_manager.get_ingest_policy = AsyncMock(return_value={
        "start_allowed": False,
        "start_reason": "ingest_already_running",
    })
    status_manager.start_ingest = AsyncMock()
    service._get_progress = AsyncMock(return_value=IngestProgress(
        document_id=document_id,
        current_step="extract",
        progress=10,
    ))

    response = await service.start_ingest(IngestRequest(document_id=document_id))

    assert response.status is DocumentStatus.PROCESSING
    status_manager.start_ingest.assert_not_awaited()
