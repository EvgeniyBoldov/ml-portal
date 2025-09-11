from __future__ import annotations
from celery import shared_task
from app.core.s3 import get_minio
from app.core.db import SessionLocal
from app.core.config import settings
from app.models.rag import RagDocuments
from .shared import log, task_metrics, RetryableError
# Avoid circular import by importing inside the task function

@shared_task(name="app.tasks.upload.watch", bind=True, autoretry_for=(RetryableError,), retry_backoff=True, retry_kwargs={"max_retries": 100})
def watch(self, document_id: str, *, key: str) -> dict:
    with task_metrics("upload.watch", "watch"):
        s3 = get_minio()
        session = SessionLocal()
        try:
            doc = session.get(RagDocuments, document_id)
            if not doc:
                return {"ok": False, "error": "doc_not_found"}
            raw_bucket = settings.S3_BUCKET_RAG
            rel = key.split(raw_bucket + "/", 1)[-1] if key.startswith(raw_bucket + "/") else key
            try:
                s3.stat_object(raw_bucket, rel)
            except Exception:
                raise RetryableError("not_uploaded_yet")
            from app.services.rag_service import start_ingest_chain
            start_ingest_chain(document_id)
            return {"ok": True, "started": "ingest"}
        finally:
            session.close()
