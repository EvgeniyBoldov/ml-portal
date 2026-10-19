"""Deliver durable LongMemory commands and publish committed progress to document SSE."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select

from app.adapters.s3_client import s3_manager
from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.long_memory_document import LongMemoryDocumentOperation
from app.models.memory_scope import DocumentMemoryScope, MemoryScope
from app.models.rag import RAGDocument
from app.models.rag_ingest import Source
from app.repositories.long_memory_document_repository import LongMemoryDocumentRepository
from app.services.hipporag_service import HippoRAGService
from app.services.long_memory_document_service import LongMemoryDocumentService
from app.services.rag_event_publisher import RAGEventPublisher
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)


async def _execute(operation_id: str) -> dict:
    settings = get_settings()
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        async with get_worker_session() as session:
            operation = await session.scalar(select(LongMemoryDocumentOperation).where(
                LongMemoryDocumentOperation.id == UUID(operation_id)).with_for_update(skip_locked=True))
            if operation is None or operation.status in {"completed", "cancelled"}:
                return {"status": "ignored"}
            if operation.status == "running" and operation.updated_at > datetime.now(timezone.utc) - timedelta(seconds=settings.HIPPO_OPERATION_LEASE_SECONDS):
                return {"status": "running"}
            document = await session.get(RAGDocument, operation.document_id)
            if operation.action == "add" and (document is None or document.long_memory_generation != operation.generation):
                operation.status = "cancelled"
                await session.commit()
                return {"status": "cancelled"}
            if document and document.long_memory_generation != operation.generation:
                operation.status = "cancelled"
                await session.commit()
                return {"status": "cancelled"}
            operation.status = "running"
            operation.attempts += 1
            await session.commit()
            service = LongMemoryDocumentService(session)

            async def progress(record: dict) -> None:
                changed = record != operation.progress
                projected = await service.project(operation, record)
                await session.commit()
                if not projected or not changed:
                    return
                publisher = RAGEventPublisher(redis)
                try:
                    for key, value in record.get("steps", {}).items():
                        await publisher.publish_status_update(doc_id=operation.document_id, tenant_id=operation.tenant_id,
                            stage=f"memory.{'knowledge' if key == 'extract' else 'graph'}", status=value["status"],
                            metrics=value.get("metrics"), error=record.get("error"))
                    document = await session.get(RAGDocument, operation.document_id)
                    if document:
                        await publisher.publish_aggregate_status(doc_id=operation.document_id, tenant_id=operation.tenant_id,
                            agg_status=document.agg_status or document.status, agg_details=document.agg_details_json)
                except Exception:
                    logger.warning("LongMemory progress SSE unavailable operation_id=%s", operation_id, exc_info=True)

            try:
                payload = None
                if operation.action == "add":
                    canonical_key = operation.payload["canonical_key"]
                    content = await s3_manager.get_object(settings.S3_BUCKET_RAG, canonical_key)
                    if content is None:
                        raise ValueError("Canonical document file is missing")
                    text = str(json.loads(content.decode("utf-8")).get("text") or "")
                    if not text.strip():
                        raise ValueError("Canonical document is empty")
                    scopes = list((await session.scalars(select(MemoryScope.key).join(
                        DocumentMemoryScope, DocumentMemoryScope.scope_id == MemoryScope.id,
                    ).where(DocumentMemoryScope.document_id == document.id))).all()) or ["company"]
                    payload = {"id": str(document.id), "content": text, "metadata": {
                        "document_title": document.title, "filename": document.filename,
                        "canonical_key": canonical_key, "scope_slugs": scopes}}
                record = await HippoRAGService(session).document_operation(operation_id=operation.id,
                    document_id=operation.document_id, generation=operation.generation, action=operation.action,
                    document=payload, on_progress=progress)
                operation.status = record["status"]
                operation.error = None
                source = await session.get(Source, operation.document_id)
                current = await service.repository.lock_document(operation.document_id)
                if source and current and current.long_memory_generation == operation.generation:
                    source.meta = {**dict(source.meta or {}), "hipporag": record}
                await session.commit()
                return {"operation_id": operation_id, "status": operation.status}
            except Exception as exc:
                await session.rollback()
                operation = await session.get(LongMemoryDocumentOperation, UUID(operation_id))
                logger.exception("LongMemory document operation failed operation_id=%s", operation_id)
                operation.status = "failed"
                operation.error = f"{type(exc).__name__}: {exc}"[:1000]
                record = {**dict(operation.progress or {}), "status": "failed", "error": operation.error}
                steps = dict(record.get("steps") or {})
                for key in ("extract", "index"):
                    value = dict(steps.get(key) or {"metrics": {}})
                    if value.get("status") != "completed":
                        value.update(status="failed", finished_at=datetime.now(timezone.utc).isoformat())
                    steps[key] = value
                record["steps"] = steps
                await progress(record)
                raise
    finally:
        await redis.aclose()


@celery_app.task(queue="memory", acks_late=True, reject_on_worker_lost=True)
def execute_long_memory_document(operation_id: str) -> dict:
    return asyncio.run(_execute(operation_id))


@celery_app.task(queue="maintenance.default", acks_late=True)
def reconcile_long_memory_documents() -> int:
    async def dispatch() -> int:
        async with get_worker_session() as session:
            ids = await LongMemoryDocumentRepository(session).recoverable()
        for operation_id in ids:
            execute_long_memory_document.delay(str(operation_id))
        return len(ids)
    return asyncio.run(dispatch())
