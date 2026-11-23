"""Unit tests for app/workers/tasks_rag_reindex.py."""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.workers import tasks_rag_reindex


def make_session() -> SimpleNamespace:
    return SimpleNamespace(commit=AsyncMock())


def make_session_scope(session: SimpleNamespace):
    @asynccontextmanager
    async def scope():
        yield session

    return scope


def make_result(**overrides) -> SimpleNamespace:
    result = SimpleNamespace(scanned=5, queued=3, skipped=1, failed=1, items=[{"doc_id": "abc"}])
    for key, value in overrides.items():
        setattr(result, key, value)
    return result


class TestReconcileStaleRagReindex:
    def test_runs_with_defaults_and_maps_result_payload(self, monkeypatch):
        session = make_session()
        orchestrator = SimpleNamespace(
            enqueue_stale_documents=AsyncMock(return_value=make_result()),
        )
        created_with = []

        class RecordingFactory:
            def __init__(self, actual_session):
                created_with.append(actual_session)
                self.enqueue_stale_documents = orchestrator.enqueue_stale_documents

        monkeypatch.setattr(tasks_rag_reindex, "get_worker_session", make_session_scope(session))
        monkeypatch.setattr(tasks_rag_reindex, "RAGBatchReindexOrchestrator", RecordingFactory)

        payload = tasks_rag_reindex.reconcile_stale_rag_reindex.run()

        assert created_with == [session]
        orchestrator.enqueue_stale_documents.assert_awaited_once_with(
            tenant_id=None,
            model_alias=None,
            limit=100,
            dry_run=False,
        )
        session.commit.assert_awaited_once()
        assert payload == {
            "tenant_id": None,
            "model_alias": None,
            "scanned": 5,
            "queued": 3,
            "skipped": 1,
            "failed": 1,
            "items": [{"doc_id": "abc"}],
        }

    def test_converts_tenant_id_and_forwards_arguments(self, monkeypatch):
        tenant_id = str(uuid.uuid4())
        session = make_session()
        orchestrator = SimpleNamespace(enqueue_stale_documents=AsyncMock(return_value=make_result(scanned=0, queued=0, items=[])))

        monkeypatch.setattr(tasks_rag_reindex, "get_worker_session", make_session_scope(session))
        monkeypatch.setattr(tasks_rag_reindex, "RAGBatchReindexOrchestrator", lambda _s: orchestrator)

        payload = tasks_rag_reindex.reconcile_stale_rag_reindex.run(
            tenant_id=tenant_id,
            model_alias="text-embed",
            limit=7,
        )

        orchestrator.enqueue_stale_documents.assert_awaited_once_with(
            tenant_id=uuid.UUID(tenant_id),
            model_alias="text-embed",
            limit=7,
            dry_run=False,
        )
        assert payload["tenant_id"] == tenant_id
        assert payload["model_alias"] == "text-embed"
        assert payload["scanned"] == 0
        assert payload["items"] == []

    def test_error_propagates_from_orchestrator(self, monkeypatch):
        session = make_session()
        orchestrator = SimpleNamespace(
            enqueue_stale_documents=AsyncMock(side_effect=RuntimeError("db down")),
        )

        monkeypatch.setattr(tasks_rag_reindex, "get_worker_session", make_session_scope(session))
        monkeypatch.setattr(tasks_rag_reindex, "RAGBatchReindexOrchestrator", lambda _s: orchestrator)

        with pytest.raises(RuntimeError, match="db down"):
            tasks_rag_reindex.reconcile_stale_rag_reindex.run()
