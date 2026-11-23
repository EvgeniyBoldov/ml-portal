"""
Unit tests for aggregate status deduplication.

Verifies that RAGStatusManager._update_aggregate_status queues a post-commit
projection event only when the user-visible status actually changes. Delivery
itself is deferred: the Redis SSE publish happens in the Celery task
`refresh_rag_status_projection` after commit, never synchronously here.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.services.rag_status_manager import (
    RAGStatusManager,
    _POST_COMMIT_QUEUE_KEY,
    _dispatch_rag_status_queue,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_prev_row(tenant_id, agg_status: str, effective_status: str | None):
    """Simulate a (tenant_id, agg_status, agg_details_json) row."""
    return (
        tenant_id,
        agg_status,
        {"effective_status": effective_status} if effective_status else {},
    )


class _FakeScalarResult:
    def __init__(self, row):
        self._row = row

    def one_or_none(self):
        return self._row


class _FakeAsyncSession:
    """Async-session facade over a real (bindless) sync Session.

    `_lock_document_row` awaits `session.scalar(...)` and the dedup read
    awaits `session.execute(...).one_or_none()`. The post-commit queue lives
    on `sync_session.info`, and SQLAlchemy event listeners require a real
    Session instance as their target.
    """

    def __init__(self, prev_row):
        self._prev_row = prev_row
        self.sync_session = Session()
        self.scalar = AsyncMock(side_effect=self._scalar)
        self.execute = AsyncMock(side_effect=self._execute)

    async def _scalar(self, stmt):
        return MagicMock(name="locked_document")

    async def _execute(self, stmt):
        return _FakeScalarResult(self._prev_row)


def _make_manager(session, publisher):
    manager = RAGStatusManager.__new__(RAGStatusManager)
    manager.session = session
    manager.event_publisher = publisher
    manager.status_repo = MagicMock()
    manager._get_target_models = AsyncMock(return_value=[])
    manager._resolve_status_model_context = AsyncMock(return_value=(None, None, {}))
    manager._get_current_model_versions = AsyncMock(return_value={})
    manager._annotate_stale_models = MagicMock()
    manager._get_current_model_fingerprints = AsyncMock(return_value={})
    manager._refresh_collection_statuses_for_document = AsyncMock()
    return manager


async def _run_update(manager, doc_id) -> None:
    with patch(
        "app.services.rag_status_manager.calculate_aggregate_status",
        return_value=("ready", {"effective_status": "ready"}),
    ):
        with patch.object(manager.status_repo, "get_pipeline_nodes", AsyncMock(return_value=[])):
            with patch.object(manager.status_repo, "get_embedding_nodes", AsyncMock(return_value=[])):
                with patch.object(manager.status_repo, "get_index_nodes", AsyncMock(return_value=[])):
                    with patch.object(manager.status_repo, "get_node", AsyncMock(return_value=None)):
                        await manager._update_aggregate_status(doc_id)


def _queued_events(session) -> list[dict]:
    payload = session.sync_session.info.get(_POST_COMMIT_QUEUE_KEY) or {}
    return payload.get("events") or []


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_event_queued_when_status_unchanged():
    """Identical agg_status and effective_status: nothing is queued for post-commit."""
    doc_id, tenant_id = uuid4(), uuid4()
    session = _FakeAsyncSession(_make_prev_row(tenant_id, "ready", "ready"))
    publisher = MagicMock()
    publisher.publish_aggregate_status = AsyncMock()

    await _run_update(_make_manager(session, publisher), doc_id)

    assert _queued_events(session) == []
    # Delivery is post-commit only: the manager must never publish directly.
    publisher.publish_aggregate_status.assert_not_called()


@pytest.mark.asyncio
async def test_event_queued_when_status_changes():
    """agg_status changed: one aggregate event is queued for post-commit delivery."""
    doc_id, tenant_id = uuid4(), uuid4()
    session = _FakeAsyncSession(_make_prev_row(tenant_id, "processing", "processing"))
    publisher = MagicMock()
    publisher.publish_aggregate_status = AsyncMock()

    await _run_update(_make_manager(session, publisher), doc_id)

    events = _queued_events(session)
    assert len(events) == 1
    assert events[0]["kind"] == "aggregate"
    assert events[0]["doc_id"] == str(doc_id)
    assert events[0]["tenant_id"] == str(tenant_id)
    assert events[0]["agg_status"] == "ready"
    # The manager queues; the Redis publish happens in the Celery worker.
    publisher.publish_aggregate_status.assert_not_called()


@pytest.mark.asyncio
async def test_post_commit_dispatch_hands_events_to_projection_task(monkeypatch: pytest.MonkeyPatch):
    """After commit the queued events go to refresh_rag_status_projection."""
    doc_id, tenant_id = uuid4(), uuid4()
    session = _FakeAsyncSession(_make_prev_row(tenant_id, "processing", "processing"))
    await _run_update(_make_manager(session, MagicMock()), doc_id)

    dispatched: list[dict] = []

    def _delay(payload: dict) -> None:
        dispatched.append(payload)

    task = MagicMock(delay=_delay)
    monkeypatch.setattr(
        "app.workers.tasks_rag_status_projection.refresh_rag_status_projection", task
    )

    _dispatch_rag_status_queue(session.sync_session)

    assert len(dispatched) == 1
    payload = dispatched[0]
    assert payload["events"][0]["kind"] == "aggregate"
    assert payload["events"][0]["agg_status"] == "ready"
    # The queue is consumed on dispatch.
    assert _POST_COMMIT_QUEUE_KEY not in session.sync_session.info
