from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Dict, Any

from celery import Task
from sqlalchemy import select

from app.celery_app import app as celery_app
from app.core.logging import get_logger
from app.models.rag import RAGDocument
from app.repositories.rag_ingest_repos import AsyncSourceRepository
from app.services.document_artifacts import (
    get_document_artifact,
    normalize_document_source_meta,
    upsert_document_artifact,
)
from app.storage.paths import get_canonical_path, calculate_text_checksum
from app.workers.tasks_rag_ingest.stage_context import IngestStageContext, run_stage
from app.workers.tasks_rag_ingest.stage_results import ExtractResult, NormalizeResult

logger = get_logger(__name__)


def smart_normalize(text: str) -> str:
    """
    Normalize text while preserving structure (paragraphs).
    1. Remove control characters (except whitespace)
    2. Replace multiple horizontal spaces with single space
    3. Replace 3+ newlines with 2 newlines (paragraph break)
    4. Trim whitespace
    """
    if not text:
        return ""
        
    # 1. Remove non-printable chars (allow newlines/tabs)
    text = "".join(ch for ch in text if ch.isprintable() or ch in ['\n', '\t', '\r'])
    
    # 2. Replace windows line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # 3. Collapse horizontal whitespace (spaces, tabs) to single space
    text = re.sub(r'[ \t]+', ' ', text)
    
    # 4. Collapse multiple newlines to max 2 (paragraph separator)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


@celery_app.task(
    queue="ingest.normalize",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def normalize_document(self: Task, extract_result: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Normalize text and convert to canonical format.

    Flow:
    1. Read extracted raw text from S3
    2. Normalize text (cleanup, unicode fix)
    3. Create canonical document structure (JSON)
    4. Upload canonical document to S3
    5. Return NormalizeResult for chunk stage
    """
    prev = ExtractResult.from_dict(extract_result) if isinstance(extract_result, dict) and "source_id" in extract_result else None
    source_id = prev.source_id if prev else str(extract_result)
    extracted_key = prev.extracted_key if prev else None

    async def _execute(ctx: IngestStageContext) -> NormalizeResult:
        # 1. Mark processing
        await ctx.set_processing()

        source_repo = AsyncSourceRepository(ctx.session, ctx.tenant_id)
        source = await source_repo.get_by_id(ctx.source_id)
        if not source:
            raise ValueError(f"Source {source_id} not found")

        # 2. Check idempotency
        cached = await ctx.check_idempotency(s3_key_field="canonical_key")
        if cached:
            logger.info(f"Normalize cached for {source_id}")
            await ctx.set_completed(metrics={"status": "already_processed", "cached": True})
            await ctx.session.commit()
            return NormalizeResult(source_id=source_id, canonical_key=cached["canonical_key"])

        # 3. Read Extracted Text
        if not extracted_key:
            raise ValueError(f"No extracted_key provided for source {source_id}")

        raw_text = (await ctx.s3_get(extracted_key)).decode("utf-8")

        # 4. Normalize
        normalized_text = smart_normalize(raw_text)
        if not normalized_text:
            logger.warning(f"Text became empty after normalization for {source_id}")
            normalized_text = ""

        source_meta = normalize_document_source_meta(source.meta)
        document_meta = source_meta.get("document", {})

        # 5. Create Canonical Document
        canonical_doc = {
            "text": normalized_text,
            "metadata": {
                "source_id": source_id,
                "tenant_id": ctx.tenant_id_str,
                "filename": document_meta.get("filename"),
                "title": document_meta.get("title"),
                "language": document_meta.get("language", "en"),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "original_size": len(raw_text),
                "normalized_size": len(normalized_text),
            },
        }

        canonical_content = json.dumps(canonical_doc, ensure_ascii=False)

        # 6. Upload Canonical
        content_checksum = calculate_text_checksum(normalized_text)
        canonical_key = get_canonical_path(ctx.tenant_id, ctx.source_id, content_checksum)

        await ctx.s3_put(
            key=canonical_key,
            content=canonical_content.encode("utf-8"),
            content_type="application/json",
        )

        # 6.1. Persist canonical artifact on Source and RAGDocument
        source.meta = upsert_document_artifact(
            source_meta,
            "canonical",
            {
                "key": canonical_key,
                "content_type": "application/json",
                "checksum": content_checksum,
                "size_bytes": len(canonical_content.encode("utf-8")),
                "format": "canonical_document_v1",
            },
        )
        ctx.session.add(source)

        document_result = await ctx.session.execute(
            select(RAGDocument).where(
                RAGDocument.id == ctx.source_id,
                RAGDocument.tenant_id == ctx.tenant_id,
            )
        )
        document = document_result.scalar_one_or_none()
        if document:
            document.s3_key_processed = canonical_key
            ctx.session.add(document)

        # 7. Complete
        await ctx.set_completed(metrics={
            "original_size": len(raw_text),
            "normalized_size": len(normalized_text),
            "reduction_ratio": round(1 - (len(normalized_text) / len(raw_text) if raw_text else 0), 2),
            "duration_sec": ctx.elapsed_sec,
        })
        await ctx.save_idempotency({
            "status": "completed",
            "canonical_key": canonical_key,
            "checksum": content_checksum,
        })
        await ctx.session.commit()

        return NormalizeResult(source_id=source_id, canonical_key=canonical_key)

    return run_stage(
        stage_name="normalize",
        source_id=source_id,
        tenant_id=tenant_id,
        celery_task=self,
        execute_fn=_execute,
    )
