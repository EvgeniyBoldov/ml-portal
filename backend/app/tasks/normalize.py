from __future__ import annotations
from celery import shared_task
from datetime import datetime
from app.core.config import settings
from app.core.s3 import get_minio
from app.core.db import SessionLocal
from app.models.rag import RagDocuments
from .shared import log, RetryableError, task_metrics

@shared_task(name="app.tasks.normalize.process", bind=True, autoretry_for=(RetryableError,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def process(self, document_id: str, *, source_key: str | None = None) -> dict:
    with task_metrics("normalize.process", "normalize"):
        s3 = get_minio()
        session = SessionLocal()
        try:
            doc = session.get(RagDocuments, document_id)
            if not doc:
                raise RetryableError("document_not_found")
            src = source_key or (doc.url_file or f"{doc.id}/source.bin")
            dst = f"{doc.id}/document.json"
            try:
                s3.put_object(settings.S3_BUCKET_CANONICAL, dst, b"{}", length=2)
            except Exception:
                from io import BytesIO
                s3.put_object(settings.S3_BUCKET_CANONICAL, dst, BytesIO(b"{}"), length=2)
            doc.url_canonical_file = dst
            doc.status = "chunking"
            doc.updated_at = datetime.utcnow()
            session.commit()
            return {"document_id": str(doc.id), "status": doc.status, "canonical_key": dst}
        finally:
            session.close()
