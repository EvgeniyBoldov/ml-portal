"""Normalization forks memory independently from the remaining RAG stages."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.workers.tasks_rag_ingest.stage_context import IngestStageContext
from app.services.long_memory_document_service import LongMemoryDocumentService


@pytest.mark.asyncio
async def test_normalize_enqueues_memory_even_while_rag_chunk_is_pending(monkeypatch):
    operation = SimpleNamespace(id=uuid4())
    enqueue = AsyncMock(return_value=operation)
    monkeypatch.setattr(LongMemoryDocumentService, 'enqueue', enqueue)
    ctx = IngestStageContext(source_id=uuid4(), tenant_id=uuid4(), stage_name='normalize',
        session=AsyncMock(), redis=AsyncMock(), settings=Mock(), repo_factory=Mock(),
        event_publisher=Mock(), status_manager=Mock())
    ctx._update_stage_run = AsyncMock()
    ctx._enqueue_next_stages = AsyncMock(return_value=['chunk-command'])
    result = await ctx.record_result({'source_id': str(ctx.source_id), 'canonical_key': 'canonical.json'})
    assert result == ['chunk-command']
    assert ctx.long_memory_operation_ids == [str(operation.id)]
    enqueue.assert_awaited_once_with(ctx.source_id, 'add', automatic=True, ingest_run_id=None)


@pytest.mark.asyncio
async def test_terminal_index_does_not_launch_memory_again(monkeypatch):
    enqueue = AsyncMock()
    monkeypatch.setattr(LongMemoryDocumentService, 'enqueue', enqueue)
    ctx = IngestStageContext(source_id=uuid4(), tenant_id=uuid4(), stage_name='index.encoder',
        session=AsyncMock(), redis=AsyncMock(), settings=Mock(), repo_factory=Mock(),
        event_publisher=Mock(), status_manager=Mock())
    ctx._update_stage_run = AsyncMock()
    ctx._enqueue_next_stages = AsyncMock(return_value=[])
    await ctx.record_result({'indexed_count': 1})
    enqueue.assert_not_awaited()
