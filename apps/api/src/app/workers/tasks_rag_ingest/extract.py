from __future__ import annotations

from typing import Any, Dict

from celery import Task

from app.celery_app import app as celery_app
from app.core.logging import get_logger
from app.repositories.rag_ingest_repos import AsyncSourceRepository
from app.services.document_artifacts import (
    get_document_artifact,
    normalize_document_source_meta,
)
from app.services.document_source_metadata_service import DocumentSourceMetadataService
from app.services.document_extraction_service import DocumentExtractionService, ExtractionRequest
from app.storage.paths import get_extracted_path, calculate_text_checksum
from app.workers.tasks_rag_ingest.stage_context import IngestStageContext, run_stage
from app.workers.tasks_rag_ingest.stage_results import ExtractResult

logger = get_logger(__name__)


def _detect_ext(filename: str) -> str:
    name = (filename or "").lower()
    if "." not in name:
        return ""
    return name[name.rfind(".") + 1:]


@celery_app.task(
    queue="ingest.extract",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def extract_document(
    self: Task, source_id: str, tenant_id: str, run_id: str | None = None, generation: int | None = None,
) -> Dict[str, Any]:
    """
    Extract text from document.

    Flow:
    1. Download original file from S3
    2. Extract text (Docling-first with local fallback)
    3. Upload extracted raw text to S3
    4. Return ExtractResult for normalize stage
    """

    async def _execute(ctx: IngestStageContext) -> ExtractResult:
        # 1. Mark processing
        await ctx.set_processing()

        source_repo = AsyncSourceRepository(ctx.session, ctx.tenant_id)
        source = await source_repo.get_by_id(ctx.source_id)
        if not source:
            raise ValueError(f"Source {source_id} not found")

        # 2. Check idempotency
        cached = await ctx.check_idempotency(s3_key_field="extracted_key")
        if cached:
            logger.info(f"Extract cached for {source_id}")
            await ctx.set_completed(metrics={"status": "already_processed", "cached": True})
            return ExtractResult(
                source_id=source_id,
                extracted_key=cached["extracted_key"],
                extractor_kind=cached.get("extractor_kind", ""),
            )

        # 3. Download Original
        source_meta = normalize_document_source_meta(source.meta)
        original_artifact = get_document_artifact(source_meta, "original")
        origin_key = original_artifact.get("key")
        if not origin_key:
            raise ValueError(f"No original artifact key found for source {source_id}")

        await ctx.session.commit()
        file_content = await ctx.s3_get(origin_key)

        # 4. Extract text
        filename = (
            source_meta.get("document", {}).get("filename")
            or original_artifact.get("filename")
            or origin_key.split("/")[-1]
        )
        ext = _detect_ext(filename)
        logger.info(
            "Starting extract stage: source_id=%s tenant_id=%s filename=%s ext=%s origin_key=%s size_bytes=%s",
            source_id,
            ctx.tenant_id_str,
            filename,
            ext,
            origin_key,
            len(file_content),
        )

        # Release the DB connection before the potentially long Docling/local
        # extraction and subsequent object-storage write.
        await ctx.session.commit()
        shared = await DocumentExtractionService().extract(
            ExtractionRequest(
                payload=file_content,
                filename=filename,
                content_type=source_meta.get("document", {}).get("content_type"),
                profile="rag_ingest",
                max_bytes=max(len(file_content), 1),
            )
        )
        extracted_text = shared.text.strip()
        extractor_kind = shared.parser
        extraction_warnings = shared.warnings
        extraction_meta = shared.meta

        if extraction_warnings:
            logger.warning(
                "Extractor warnings: source_id=%s filename=%s extractor=%s warnings=%s",
                source_id,
                filename,
                extractor_kind,
                extraction_warnings,
            )

        if not extracted_text:
            warning_suffix = f" Warnings: {' | '.join(extraction_warnings)}" if extraction_warnings else ""
            raise ValueError(f"Failed to extract text from {filename}.{warning_suffix}")

        # 5. Upload Artifact
        text_checksum = calculate_text_checksum(extracted_text)
        extracted_key = get_extracted_path(ctx.tenant_id, ctx.source_id, text_checksum)

        await ctx.s3_put(
            key=extracted_key,
            content=extracted_text.encode("utf-8"),
            content_type="text/plain",
        )

        published = await DocumentSourceMetadataService(ctx.session).upsert_artifact(
            ctx.source_id,
            ctx.tenant_id,
            "extracted",
            {
                "key": extracted_key,
                "content_type": "text/plain",
                "checksum": text_checksum,
                "size_bytes": len(extracted_text.encode("utf-8")),
                "extractor_kind": extractor_kind,
            },
        )
        if published is None:
            raise ValueError(f"Source {source_id} disappeared before extracted artifact publication")

        # 6. Complete
        metrics = {
            "word_count": len(extracted_text.split()),
            "char_count": len(extracted_text),
            "extractor": extractor_kind,
            "checksum": text_checksum,
            "duration_sec": ctx.elapsed_sec,
            "file_size_bytes": len(file_content),
        }
        if extraction_meta:
            metrics.update(extraction_meta)

        await ctx.set_completed(metrics=metrics)
        await ctx.save_idempotency({
            "status": "completed",
            "extracted_key": extracted_key,
            "checksum": text_checksum,
            "extractor_kind": extractor_kind,
        })

        return ExtractResult(
            source_id=source_id,
            extracted_key=extracted_key,
            extractor_kind=extractor_kind,
            warnings=extraction_warnings,
        )

    return run_stage(
        stage_name="extract",
        source_id=source_id,
        tenant_id=tenant_id,
        celery_task=self,
        execute_fn=_execute,
        run_id=run_id,
        generation=generation,
    )
