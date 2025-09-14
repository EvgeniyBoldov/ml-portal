from __future__ import annotations

import json
from typing import Optional
from celery import shared_task

from app.core.config import settings  # expects settings.S3_BUCKET_RAG
from app.core.s3 import get_object, put_object  # S3 functions
from app.core.metrics import rag_ingest_stage_duration, rag_ingest_errors_total

from app.services.enhanced_text_extractor import extract_text_enhanced
from app.services.text_normalizer import normalize_text
from .shared import log, RetryableError, task_metrics

@shared_task(name="app.tasks.normalize.normalize", bind=True, autoretry_for=(RetryableError,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def normalize(self, document_id: str, source_key: Optional[str] = None, original_filename: Optional[str] = None) -> dict:
    """
    Read original file from S3, extract + normalize text, and write canonical JSON to
    f"{document_id}/canonical.txt" in the same RAG bucket.
    Returns a dict with canonical path and counters for logging/metrics.
    """
    with task_metrics("normalize.normalize", "normalize"):
        try:
            # 1) Determine keys
            bucket = settings.S3_BUCKET_RAG
            if source_key is None:
                raise ValueError("source_key is required to locate the original file in S3")
            canonical_key = f"{document_id}/canonical.txt"

            # 2) Load original bytes
            obj = get_object(bucket, source_key)
            content = obj.read()

            # 3) Extract text by format, normalize
            filename = original_filename or source_key.split("/")[-1]
            result = extract_text_enhanced(content, filename=filename)
            cleaned = normalize_text(result.text)

            # 4) Build canonical JSON payload with tables
            canonical_payload = {
                "text": cleaned,
                "tables": [{"name": t.name, "csv": t.csv_data, "rows": t.rows, "cols": t.cols} for t in result.tables],
                "meta": result.meta,
                "original_filename": filename,
                "extractor": result.kind,
                "warnings": result.warnings,
            }
            data = json.dumps(canonical_payload, ensure_ascii=False).encode("utf-8")

            # 5) Store canonical alongside original (same bucket)
            put_object(bucket, canonical_key, data, content_type="application/json; charset=utf-8")

            # Обновляем метрики
            rag_ingest_stage_duration.labels(stage="normalize").observe(0.1)  # Примерное время

            return {
                "document_id": document_id,
                "source_key": source_key,
                "canonical_key": canonical_key,
                "text_chars": len(cleaned),
                "extractor": result.kind,
                "warnings": result.warnings,
            }
            
        except Exception as e:
            log.error(f"Normalization failed for document {document_id}: {e}")
            rag_ingest_errors_total.labels(stage="normalize", error_type="processing_failed").inc()
            raise RetryableError(f"Normalization failed: {e}")

# Оставляем старую функцию для обратной совместимости
def process(document_id: str, source_key: Optional[str] = None, original_filename: Optional[str] = None) -> dict:
    """Legacy function for backward compatibility"""
    return normalize.delay(document_id, source_key, original_filename).get()
