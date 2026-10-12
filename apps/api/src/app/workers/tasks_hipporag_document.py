"""Native HippoRAG indexing after the existing document RAG pipeline."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from celery import Task
from sqlalchemy import update, text

from app.adapters.s3_client import s3_manager
from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.rag import RAGDocument
from app.models.rag_ingest import Source, RAGIngestStageOutbox
from app.services.hipporag_service import HippoRAGService
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)


@celery_app.task(queue="memory", bind=True, acks_late=True, reject_on_worker_lost=True,
                autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def index_hipporag_document(self: Task, index_results: Any, tenant_id: str,
                           manual_request_id: str | None = None,
                           ingest_run_id: str | None = None) -> dict[str, Any]:
    rows = index_results if isinstance(index_results, list) else [index_results]
    source_id = next((str(row["source_id"]) for row in rows if isinstance(row, dict) and row.get("source_id")), "")
    if not source_id:
        raise ValueError("HippoRAG indexing requires a source_id")

    async def execute() -> dict[str, Any]:
        async with get_worker_session() as session:
            document = await session.get(RAGDocument, UUID(source_id))
            source = await session.get(Source, UUID(source_id))
            if document is None or source is None or not document.s3_key_processed:
                raise ValueError("Canonical document is unavailable for HippoRAG indexing")
            payload = await s3_manager.get_object(get_settings().S3_BUCKET_RAG, document.s3_key_processed)
            if payload is None:
                raise ValueError("Canonical document file is missing")
            canonical = json.loads(payload.decode("utf-8"))
            text = str(canonical.get("text") or "")
            if not text.strip():
                raise ValueError("Canonical document is empty")
            result = await HippoRAGService(session).index_document(document_id=document.id, text=text,
                metadata={"document_title": document.title, "filename": document.filename,
                          "canonical_key": document.s3_key_processed})
            source.meta = {**dict(source.meta or {}), "hipporag": {"status": "indexed", **result}}
            if ingest_run_id:
                await session.execute(update(RAGIngestStageOutbox).where(
                    RAGIngestStageOutbox.run_id == UUID(ingest_run_id),
                    RAGIngestStageOutbox.stage_key.in_(("hipporag", "shadow")),
                ).values(status="completed"))
            await session.commit()
            logger.info("HippoRAG document indexed source_id=%s task_id=%s document_count=%s",
                        source_id, self.request.id, result.get("document_count"))
            return {"source_id": source_id, "status": "indexed", **result}

    return asyncio.run(execute())


@celery_app.task(queue="memory", acks_late=True, reject_on_worker_lost=True)
def reconcile_long_memory_reindex() -> dict[str, Any]:
    """Consume committed selection requests; crashes leave requests retryable."""
    async def execute() -> dict[str, Any]:
        async with get_worker_session() as session:
            # Hold one queue row transactionally, even while the worker builds.
            row = (await session.execute(text("""SELECT id, model_id FROM long_memory_reindex_requests
                WHERE status IN ('pending', 'failed') AND attempts < 3
                ORDER BY created_at DESC LIMIT 1 FOR UPDATE SKIP LOCKED"""))).mappings().first()
            if row is None:
                return {"status": "idle"}
            selected = await session.scalar(text("SELECT id FROM models WHERE use_for_long_memory IS TRUE"))
            if selected != row["model_id"]:
                status, error = "superseded", None
            else:
                try:
                    result = await HippoRAGService(session).reindex_embeddings()
                    status, error = "completed", None
                    logger.info("LongMemory embeddings rebuilt model_id=%s result=%s", selected, result)
                except Exception as exc:
                    status, error = "failed", str(exc)[:2000]
                    logger.exception("LongMemory reindex failed model_id=%s", selected)
            await session.execute(text("""UPDATE long_memory_reindex_requests SET status=:status,
                attempts=attempts+1, error=:error, updated_at=now() WHERE id=:id"""),
                {"status": status, "error": error, "id": row["id"]})
            await session.commit()
            return {"status": status, "request_id": str(row["id"])}
    return asyncio.run(execute())
