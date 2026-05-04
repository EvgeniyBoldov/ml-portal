from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.repositories.rag_status_repo import AsyncRAGStatusRepository


@pytest.mark.asyncio
async def test_upsert_node_preserves_model_version_when_not_passed():
    session = AsyncMock()
    repo = AsyncRAGStatusRepository(session)

    existing = SimpleNamespace(
        status="processing",
        celery_task_id="task-1",
        model_version="1.0",
        modality="embedding",
        error_short=None,
        metrics_json=None,
        started_at=None,
        finished_at=None,
        updated_at=datetime.now(timezone.utc),
    )
    repo.get_node = AsyncMock(return_value=existing)  # type: ignore[method-assign]

    await repo.upsert_node(
        doc_id=uuid4(),
        node_type="embedding",
        node_key="all-MiniLM-L6-v2",
        status="completed",
        model_version=None,
        modality=None,
    )

    assert existing.status == "completed"
    assert existing.model_version == "1.0"
    assert existing.modality == "embedding"

