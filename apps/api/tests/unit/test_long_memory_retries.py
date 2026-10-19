"""Duplicate Celery delivery must respect the durable operation retry budget."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.workers import tasks_long_memory_documents as tasks


@pytest.mark.asyncio
@pytest.mark.parametrize("case,expected", [("permanent", "failed"), ("cooldown", "deferred"),
                                          ("exhausted", "exhausted"), ("active", "running")])
async def test_duplicate_delivery_cannot_bypass_retry_policy(monkeypatch, case, expected):
    now = datetime.now(timezone.utc)
    operation = NS(status="failed", attempts=1, updated_at=now, progress={})
    if case == "permanent":
        operation.progress = {"retryable": False}
    elif case == "cooldown":
        operation.progress = {"retryable": True, "next_retry_at": (now + timedelta(minutes=5)).isoformat()}
    elif case == "exhausted":
        operation.attempts = 4
    else:
        operation.status = "running"
    session = NS(scalar=AsyncMock(return_value=operation), get=AsyncMock(), commit=AsyncMock())
    @asynccontextmanager
    async def session_factory():
        yield session
    redis = NS(aclose=AsyncMock())
    monkeypatch.setattr(tasks, "get_worker_session", session_factory)
    monkeypatch.setattr(tasks, "get_settings", lambda: NS(REDIS_URL="redis://unused",
        HIPPO_OPERATION_LEASE_SECONDS=60, HIPPO_OPERATION_MAX_ATTEMPTS=4))
    monkeypatch.setattr(tasks, "Redis", NS(from_url=lambda *args, **kwargs: redis))
    assert await tasks._execute(str(uuid4())) == {"status": expected}
    session.get.assert_not_awaited()
    session.commit.assert_not_awaited()
    redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("retryable", [True, False])
async def test_worker_persists_failure_classification_and_provider_cooldown(monkeypatch, retryable):
    now = datetime.now(timezone.utc)
    operation = NS(id=uuid4(), document_id=uuid4(), tenant_id=uuid4(), generation=1, action="add",
        status="pending", attempts=0, updated_at=now, progress={}, payload={"canonical_key": "canonical.json"})
    document = NS(id=operation.document_id, long_memory_generation=1, title="Document", filename="doc.txt")
    session = AsyncMock()
    session.scalar.return_value = operation
    session.scalars.return_value = NS(all=lambda: ["company"])
    session.get.side_effect = lambda model, _: operation if model is tasks.LongMemoryDocumentOperation else document
    @asynccontextmanager
    async def session_factory():
        yield session
    async def project(row, record):
        row.progress = record
        return False  # SSE does not affect durable status persistence.
    service = NS(project=AsyncMock(side_effect=project))
    async def failed_operation(**kwargs):
        await kwargs["on_progress"]({"status": "failed", "retryable": retryable,
            "error_code": "llm_rate_limited" if retryable else "llm_authentication_error",
            "retry_after_seconds": 120, "steps": {"extract": {"status": "failed"}}})
        raise RuntimeError("Safe LLM failure")
    redis = NS(aclose=AsyncMock())
    monkeypatch.setattr(tasks, "get_worker_session", session_factory)
    monkeypatch.setattr(tasks, "get_settings", lambda: NS(REDIS_URL="redis://unused", S3_BUCKET_RAG="rag",
        HIPPO_OPERATION_LEASE_SECONDS=60, HIPPO_OPERATION_MAX_ATTEMPTS=4, HIPPO_OPERATION_RETRY_DELAY_SECONDS=60))
    monkeypatch.setattr(tasks, "Redis", NS(from_url=lambda *args, **kwargs: redis))
    monkeypatch.setattr(tasks, "s3_manager", NS(get_object=AsyncMock(return_value=b'{"text":"Source"}')))
    monkeypatch.setattr(tasks, "LongMemoryDocumentService", lambda _: service)
    monkeypatch.setattr(tasks, "HippoRAGService", lambda _: NS(document_operation=failed_operation))
    with pytest.raises(RuntimeError, match="Safe LLM failure"):
        await tasks._execute(str(operation.id))
    assert operation.status == "failed"
    assert operation.attempts == 1
    assert operation.progress["retryable"] is retryable
    assert "Safe LLM failure" in operation.error
    assert operation.progress["steps"]["extract"]["status"] == "failed"
    if retryable:
        assert datetime.fromisoformat(operation.progress["next_retry_at"]) >= now + timedelta(seconds=120)
    else:
        assert "next_retry_at" not in operation.progress
    session.rollback.assert_awaited_once()
    assert session.commit.await_count >= 2
