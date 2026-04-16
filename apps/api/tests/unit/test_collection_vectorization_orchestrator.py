from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.services.collection_vectorization_orchestrator import (
    CollectionVectorizationOrchestrator,
)
from app.workers.tasks_collection_vectorize import _collection_lock_key


def test_enqueue_normalizes_row_ids_and_returns_task_id(monkeypatch):
    apply_async = MagicMock(return_value=SimpleNamespace(id="task-123"))
    monkeypatch.setattr(
        "app.workers.tasks_collection_vectorize.vectorize_collection_rows",
        SimpleNamespace(apply_async=apply_async),
    )

    task_id = CollectionVectorizationOrchestrator.enqueue(
        collection_id=uuid4(),
        tenant_id=uuid4(),
        row_ids=["row-1", "row-1", " row-2 "],
        countdown=7,
    )

    assert task_id == "task-123"
    apply_async.assert_called_once()
    args = apply_async.call_args.kwargs["args"]
    assert args[2] == ["row-1", "row-2"]
    assert apply_async.call_args.kwargs["countdown"] == 7


@pytest.mark.asyncio
async def test_enqueue_for_collection_skips_when_vector_search_disabled():
    orchestrator = CollectionVectorizationOrchestrator(session=MagicMock())
    collection = SimpleNamespace(
        id=uuid4(),
        has_vector_search=False,
        qdrant_collection_name=None,
    )

    task_id = await orchestrator.enqueue_for_collection(
        collection=collection,
        tenant_id=uuid4(),
    )

    assert task_id is None


@pytest.mark.asyncio
async def test_enqueue_for_collection_emits_outbox_event(monkeypatch):
    session = MagicMock()
    orchestrator = CollectionVectorizationOrchestrator(session=session)
    collection = SimpleNamespace(
        id=uuid4(),
        has_vector_search=True,
        qdrant_collection_name="coll_test_docs",
    )
    emit_event = AsyncMock()
    monkeypatch.setattr(
        "app.services.collection_vectorization_orchestrator.emit_collection_vectorization_requested",
        emit_event,
    )
    monkeypatch.setattr(
        CollectionVectorizationOrchestrator,
        "enqueue",
        staticmethod(lambda **_kwargs: "task-321"),
    )

    task_id = await orchestrator.enqueue_for_collection(
        collection=collection,
        tenant_id=uuid4(),
        row_ids=["row-1", "row-1"],
        reason="row_update",
    )

    assert task_id == "task-321"
    emit_event.assert_awaited_once()
    assert emit_event.await_args.kwargs["row_ids"] == ["row-1"]
    assert emit_event.await_args.kwargs["reason"] == "row_update"


@pytest.mark.asyncio
async def test_prepare_full_revectorization_resets_state(monkeypatch):
    session = MagicMock()
    session.flush = AsyncMock()
    orchestrator = CollectionVectorizationOrchestrator(session=session)
    collection = SimpleNamespace(
        id=uuid4(),
        has_vector_search=True,
        qdrant_collection_name="coll_test_docs",
    )
    reset_state = AsyncMock()
    sync_status = AsyncMock()

    class FakeCollectionService:
        def __init__(self, _session):
            self.session = _session

        async def _reset_table_vector_state(self, current_collection):
            await reset_state(current_collection)

        async def sync_collection_status(self, current_collection, *, persist):
            await sync_status(current_collection, persist=persist)

    monkeypatch.setattr(
        "app.services.collection_service.CollectionService",
        FakeCollectionService,
    )

    await orchestrator.prepare_full_revectorization(collection)

    reset_state.assert_awaited_once_with(collection)
    sync_status.assert_awaited_once_with(collection, persist=False)
    session.flush.assert_awaited_once()


def test_collection_lock_key_is_deterministic():
    collection_id = str(uuid4())
    assert _collection_lock_key(collection_id) == _collection_lock_key(collection_id)


@pytest.mark.asyncio
async def test_reconcile_pending_collections_enqueues_only_vectorizable(monkeypatch):
    session = MagicMock()
    collection_ready = SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        has_vector_search=True,
        qdrant_collection_name="coll_ready",
    )
    collection_skipped = SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        has_vector_search=False,
        qdrant_collection_name=None,
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [collection_ready, collection_skipped]
    session.execute = AsyncMock(return_value=execute_result)

    orchestrator = CollectionVectorizationOrchestrator(session=session)
    enqueue_for_collection = AsyncMock(side_effect=["task-1", None])
    monkeypatch.setattr(orchestrator, "enqueue_for_collection", enqueue_for_collection)

    result = await orchestrator.reconcile_pending_collections(limit=10, countdown=1)

    assert result["queued_count"] == 1
    assert result["queued"][0]["collection_id"] == str(collection_ready.id)
    assert result["queued"][0]["task_id"] == "task-1"
