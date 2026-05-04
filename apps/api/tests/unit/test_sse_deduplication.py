"""
Unit tests for aggregate status deduplication (Этап 1).

Verifies that publish_aggregate_status is NOT called when agg_status
and effective_status are unchanged between updates.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_db_row(tenant_id, agg_status: str, effective_status: str | None):
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


class _FakeExecuteResult:
    def __init__(self):
        pass


class _FakeSession:
    def __init__(self, prev_row, tenant_id):
        self._prev_row = prev_row
        self._tenant_id = tenant_id
        self.execute = AsyncMock(side_effect=self._execute)

    async def _execute(self, stmt):
        stmt_str = str(stmt)
        if "agg_status" in stmt_str.lower() or "tenant_id" in stmt_str.lower():
            return _FakeScalarResult(self._prev_row)
        return _FakeExecuteResult()


@pytest.mark.asyncio
async def test_no_publish_when_status_unchanged():
    """If agg_status and effective_status are identical, no event should be published."""
    doc_id = uuid4()
    tenant_id = uuid4()
    prev_row = _make_db_row(tenant_id, "ready", "ready")

    publisher = MagicMock()
    publisher.publish_aggregate_status = AsyncMock()

    session = _FakeSession(prev_row, tenant_id)

    from app.services.rag_status_manager import RAGStatusManager

    manager = RAGStatusManager.__new__(RAGStatusManager)
    manager.session = session
    manager.event_publisher = publisher
    manager.status_repo = MagicMock()
    manager._get_target_models = AsyncMock(return_value=[])
    manager._resolve_status_model_context = AsyncMock(return_value=(None, None, {}))
    manager._get_current_model_versions = AsyncMock(return_value={})
    manager._annotate_stale_models = MagicMock()
    manager._refresh_collection_statuses_for_document = AsyncMock()

    with patch("app.services.rag_status_manager.calculate_aggregate_status", return_value=("ready", {"effective_status": "ready"})):
        with patch.object(manager.status_repo, "get_pipeline_nodes", AsyncMock(return_value=[])):
            with patch.object(manager.status_repo, "get_embedding_nodes", AsyncMock(return_value=[])):
                with patch.object(manager.status_repo, "get_index_nodes", AsyncMock(return_value=[])):
                    with patch.object(manager.status_repo, "get_node", AsyncMock(return_value=None)):
                        await manager._update_aggregate_status(doc_id)

    publisher.publish_aggregate_status.assert_not_called()


@pytest.mark.asyncio
async def test_publishes_when_status_changes():
    """If agg_status changes, publish_aggregate_status MUST be called."""
    doc_id = uuid4()
    tenant_id = uuid4()
    prev_row = _make_db_row(tenant_id, "processing", "processing")

    publisher = MagicMock()
    publisher.publish_aggregate_status = AsyncMock()

    session = _FakeSession(prev_row, tenant_id)

    from app.services.rag_status_manager import RAGStatusManager

    manager = RAGStatusManager.__new__(RAGStatusManager)
    manager.session = session
    manager.event_publisher = publisher
    manager.status_repo = MagicMock()
    manager._get_target_models = AsyncMock(return_value=[])
    manager._resolve_status_model_context = AsyncMock(return_value=(None, None, {}))
    manager._get_current_model_versions = AsyncMock(return_value={})
    manager._annotate_stale_models = MagicMock()
    manager._refresh_collection_statuses_for_document = AsyncMock()

    with patch("app.services.rag_status_manager.calculate_aggregate_status", return_value=("ready", {"effective_status": "ready"})):
        with patch.object(manager.status_repo, "get_pipeline_nodes", AsyncMock(return_value=[])):
            with patch.object(manager.status_repo, "get_embedding_nodes", AsyncMock(return_value=[])):
                with patch.object(manager.status_repo, "get_index_nodes", AsyncMock(return_value=[])):
                    with patch.object(manager.status_repo, "get_node", AsyncMock(return_value=None)):
                        await manager._update_aggregate_status(doc_id)

    publisher.publish_aggregate_status.assert_called_once()
    call_kwargs = publisher.publish_aggregate_status.call_args.kwargs
    assert call_kwargs["agg_status"] == "ready"
