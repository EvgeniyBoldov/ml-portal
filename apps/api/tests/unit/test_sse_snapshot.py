"""
Unit tests for SSE snapshot builders (Этап 2).
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.rag_status_snapshot import build_collection_snapshot, build_document_status_graph


def _make_doc(doc_id, name, agg_status, agg_details=None):
    doc = MagicMock()
    doc.id = doc_id
    doc.name = name
    doc.filename = f"{name}.pdf"
    doc.status = "active"
    doc.agg_status = agg_status
    doc.agg_details_json = agg_details or {}
    doc.updated_at = datetime.now(timezone.utc)
    return doc


class _ScalarResult:
    def __init__(self, docs):
        self._docs = docs

    def scalars(self):
        return self

    def all(self):
        return self._docs


@pytest.mark.asyncio
async def test_build_collection_snapshot_returns_all_docs():
    collection_id = uuid4()
    doc1 = _make_doc(uuid4(), "Doc A", "ready", {"effective_status": "ready"})
    doc2 = _make_doc(uuid4(), "Doc B", "processing", {"effective_status": "processing"})

    session = MagicMock()
    session.execute = AsyncMock(return_value=_ScalarResult([doc1, doc2]))

    result = await build_collection_snapshot(session, collection_id)

    assert len(result) == 2
    doc_ids = {r["document_id"] for r in result}
    assert str(doc1.id) in doc_ids
    assert str(doc2.id) in doc_ids


@pytest.mark.asyncio
async def test_build_collection_snapshot_includes_agg_status():
    collection_id = uuid4()
    doc = _make_doc(uuid4(), "Test Doc", "failed", {"effective_status": "failed", "effective_reason": "extract error"})

    session = MagicMock()
    session.execute = AsyncMock(return_value=_ScalarResult([doc]))

    result = await build_collection_snapshot(session, collection_id)

    assert len(result) == 1
    item = result[0]
    assert item["agg_status"] == "failed"
    assert item["agg_details"].get("effective_status") == "failed"


@pytest.mark.asyncio
async def test_build_collection_snapshot_empty_collection():
    collection_id = uuid4()
    session = MagicMock()
    session.execute = AsyncMock(return_value=_ScalarResult([]))

    result = await build_collection_snapshot(session, collection_id)
    assert result == []


@pytest.mark.asyncio
async def test_build_collection_snapshot_falls_back_to_status():
    """If agg_status is None, should fall back to doc.status."""
    collection_id = uuid4()
    doc = _make_doc(uuid4(), "No Agg Status", None)
    doc.agg_status = None
    doc.status = "active"

    session = MagicMock()
    session.execute = AsyncMock(return_value=_ScalarResult([doc]))

    result = await build_collection_snapshot(session, collection_id)

    assert result[0]["agg_status"] == "active"


@pytest.mark.asyncio
async def test_document_graph_uses_archive_policy_for_aggregate_status(monkeypatch):
    from app.services import rag_status_manager, rag_status_snapshot

    status_repo = SimpleNamespace(
        get_pipeline_nodes=AsyncMock(return_value=[]),
        get_embedding_nodes=AsyncMock(return_value=[]),
        get_index_nodes=AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(rag_status_snapshot, "document_memory_nodes", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        "app.repositories.rag_status_repo.AsyncRAGStatusRepository",
        lambda _session: status_repo,
    )

    class StatusManager:
        def __init__(self, *_args):
            pass

        async def _get_target_models(self, _doc_id):
            return []

        async def get_ingest_policy(self, _doc_id):
            return {
                "archived": True,
                "start_allowed": False,
                "start_reason": "document_archived",
                "active_stages": [],
                "retryable_stages": [],
                "stoppable_stages": [],
                "controls": [],
            }

    monkeypatch.setattr(rag_status_manager, "RAGStatusManager", StatusManager)
    graph = await build_document_status_graph(AsyncMock(), uuid4(), SimpleNamespace())

    assert graph is not None
    assert graph["agg_status"] == "archived"
    assert graph["ingest_policy"]["archived"] is True
