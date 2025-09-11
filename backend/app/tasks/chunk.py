from __future__ import annotations
from celery import shared_task
from datetime import datetime
from app.core.config import settings
from app.core.s3 import get_minio
from app.core.db import SessionLocal
from app.core.metrics import rag_chunks_created_total
from app.models.rag import RagDocuments, RagChunks
from .shared import log, RetryableError, task_metrics, env_int

def _split_text(txt: str, max_chars: int, overlap: int):
    i = 0; n = len(txt)
    while i < n:
        j = min(i + max_chars, n)
        yield txt[i:j]
        if j >= n: break
        i = j - overlap if j - overlap > i else j

@shared_task(name="app.tasks.chunk.split", bind=True, autoretry_for=(RetryableError,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def split(self, result: dict, *, max_chars: int | None = None, overlap: int | None = None) -> dict:
    with task_metrics("chunk.split", "chunk"):
        session = SessionLocal()
        s3 = get_minio()
        try:
            # Получаем document_id из результата предыдущей задачи
            document_id = result.get("document_id")
            if not document_id:
                raise RetryableError("no_document_id")
            
            from uuid import UUID
            doc = session.get(RagDocuments, UUID(document_id))
            if not doc or not doc.url_canonical_file:
                raise RetryableError("canonical_not_ready")
            max_chars = max_chars or env_int("CHUNK_MAX_CHARS", 1200)
            overlap   = overlap   or env_int("CHUNK_OVERLAP", 100)
            try:
                obj = s3.get_object(settings.S3_BUCKET_CANONICAL, doc.url_canonical_file)
                json_data = obj.read().decode("utf-8") or "{}"
                import json
                parsed_data = json.loads(json_data)
                # Извлекаем текст из нормализованного JSON
                data = parsed_data.get("text", "") if isinstance(parsed_data, dict) else ""
            except Exception as e:
                log.error(f"Error reading canonical file: {e}")
                data = ""
            chunks = list(_split_text(data, max_chars=max_chars, overlap=overlap)) or [""]
            for idx, text in enumerate(chunks):
                session.add(RagChunks(document_id=doc.id, chunk_idx=idx, text=text))
            rag_chunks_created_total.inc(len(chunks))
            doc.status = "embedding"; doc.updated_at = datetime.utcnow()
            session.commit()
            return {"document_id": str(doc.id), "chunks": len(chunks), "status": doc.status}
        finally:
            session.close()
