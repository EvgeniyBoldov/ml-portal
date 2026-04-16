"""
Contract tests for RAG ingest guards (check_ingest_allowed).

Validates:
- Allows ingest when all stages are pending/completed/failed
- Blocks ingest when any stage is processing or queued
- Blocks ingest for archived documents
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from types import SimpleNamespace

from app.services.rag_status_manager import RAGStatusManager, StageStatus


def _make_node(node_type: str, node_key: str, status: str):
    """Create a fake status node."""
    return SimpleNamespace(
        node_type=node_type,
        node_key=node_key,
        status=status,
    )


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def mock_repo_factory():
    return MagicMock()


@pytest.fixture
def status_manager(mock_session, mock_repo_factory):
    mgr = RAGStatusManager(mock_session, mock_repo_factory)
    mgr.status_repo = MagicMock()
    mgr.status_repo.get_pipeline_nodes = AsyncMock(return_value=[])
    mgr.status_repo.get_embedding_nodes = AsyncMock(return_value=[])
    mgr.status_repo.get_index_nodes = AsyncMock(return_value=[])
    mgr.status_repo.get_node = AsyncMock(return_value=None)
    return mgr


class TestIngestAllowed:
    """check_ingest_allowed returns allowed=True when safe."""

    @pytest.mark.asyncio
    async def test_allowed_when_no_nodes(self, status_manager):
        result = await status_manager.check_ingest_allowed(uuid4())
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_allowed_when_all_completed(self, status_manager):
        doc_id = uuid4()
        status_manager.status_repo.get_pipeline_nodes.return_value = [
            _make_node("pipeline", "extract", StageStatus.COMPLETED.value),
            _make_node("pipeline", "normalize", StageStatus.COMPLETED.value),
            _make_node("pipeline", "chunk", StageStatus.COMPLETED.value),
        ]
        result = await status_manager.check_ingest_allowed(doc_id)
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_allowed_when_all_failed(self, status_manager):
        doc_id = uuid4()
        status_manager.status_repo.get_pipeline_nodes.return_value = [
            _make_node("pipeline", "extract", StageStatus.FAILED.value),
        ]
        result = await status_manager.check_ingest_allowed(doc_id)
        assert result["allowed"] is True

    @pytest.mark.asyncio
    async def test_allowed_when_all_pending(self, status_manager):
        doc_id = uuid4()
        status_manager.status_repo.get_pipeline_nodes.return_value = [
            _make_node("pipeline", "extract", StageStatus.PENDING.value),
            _make_node("pipeline", "normalize", StageStatus.PENDING.value),
        ]
        result = await status_manager.check_ingest_allowed(doc_id)
        assert result["allowed"] is True


class TestIngestBlocked:
    """check_ingest_allowed returns allowed=False when unsafe."""

    @pytest.mark.asyncio
    async def test_blocked_when_processing(self, status_manager):
        doc_id = uuid4()
        status_manager.status_repo.get_pipeline_nodes.return_value = [
            _make_node("pipeline", "extract", StageStatus.PROCESSING.value),
        ]
        result = await status_manager.check_ingest_allowed(doc_id)
        assert result["allowed"] is False
        assert result["reason"] == "ingest_already_running"
        assert "extract" in result["active_stages"]

    @pytest.mark.asyncio
    async def test_blocked_when_queued(self, status_manager):
        doc_id = uuid4()
        status_manager.status_repo.get_pipeline_nodes.return_value = [
            _make_node("pipeline", "chunk", StageStatus.QUEUED.value),
        ]
        result = await status_manager.check_ingest_allowed(doc_id)
        assert result["allowed"] is False
        assert result["reason"] == "ingest_already_running"

    @pytest.mark.asyncio
    async def test_blocked_when_embedding_processing(self, status_manager):
        doc_id = uuid4()
        status_manager.status_repo.get_embedding_nodes.return_value = [
            _make_node("embedding", "model-1", StageStatus.PROCESSING.value),
        ]
        result = await status_manager.check_ingest_allowed(doc_id)
        assert result["allowed"] is False
        assert "embed.model-1" in result["active_stages"]

    @pytest.mark.asyncio
    async def test_blocked_when_index_queued(self, status_manager):
        doc_id = uuid4()
        status_manager.status_repo.get_index_nodes.return_value = [
            _make_node("index", "model-1", StageStatus.QUEUED.value),
        ]
        result = await status_manager.check_ingest_allowed(doc_id)
        assert result["allowed"] is False
        assert "index.model-1" in result["active_stages"]

    @pytest.mark.asyncio
    async def test_blocked_when_archived(self, status_manager):
        doc_id = uuid4()
        # No active stages, but document is archived
        status_manager.status_repo.get_node.return_value = SimpleNamespace(
            node_type="archive", node_key="archive", status="completed"
        )
        result = await status_manager.check_ingest_allowed(doc_id)
        assert result["allowed"] is False
        assert result["reason"] == "document_archived"
