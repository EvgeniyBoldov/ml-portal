from __future__ import annotations

from typing import Any, Dict

from celery import Task
from sqlalchemy import select

from app.celery_app import app as celery_app
from app.core.logging import get_logger
from app.models.model_registry import Model, ModelType, ModelStatus
from app.models.tenant import Tenants
from app.repositories.rag_ingest_repos import AsyncSourceRepository
from app.services.document_artifacts import (
    get_document_artifact,
    normalize_document_source_meta,
    upsert_document_artifact,
)
from app.services.extractors import ExtractorRegistry
from app.storage.paths import get_extracted_path, calculate_text_checksum
from app.workers.tasks_rag_ingest.stage_context import IngestStageContext, run_stage
from app.workers.tasks_rag_ingest.stage_results import ExtractResult

logger = get_logger(__name__)


async def _resolve_extractor(ctx: IngestStageContext, ext: str) -> Any:
    """
    Resolve the right extractor based on tenant settings.

    If tenant.layout=True and file is PDF → use LayoutPdfExtractor.
    Otherwise → use default ExtractorRegistry lookup.
    """
    if ext != "pdf":
        return ExtractorRegistry.get_extractor(ext)

    result = await ctx.session.execute(
        select(Tenants).where(Tenants.id == ctx.tenant_id)
    )
    tenant = result.scalar_one_or_none()

    if tenant and tenant.layout:
        from app.services.extractors.layout_pdf import LayoutPdfExtractor
        model_result = await ctx.session.execute(
            select(Model).where(
                Model.type == ModelType.OCR,
                Model.default_for_type == True,
                Model.enabled == True,
                Model.status == ModelStatus.AVAILABLE,
                Model.deleted_at.is_(None),
            ).limit(1)
        )
        layout_model = model_result.scalar_one_or_none()
        engine_config = layout_model.extra_config if layout_model and layout_model.extra_config else {}
        logger.info(f"Using layout-aware PDF extractor for tenant {ctx.tenant_id_str}")
        return LayoutPdfExtractor(engine_config=engine_config)

    return ExtractorRegistry.get_extractor(ext)


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
def extract_document(self: Task, source_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Extract text from document.

    Flow:
    1. Download original file from S3
    2. Resolve extractor (layout-aware if tenant.layout=True)
    3. Extract text (preserving structure if possible)
    4. Upload extracted raw text to S3
    5. Return ExtractResult for normalize stage
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
            await ctx.session.commit()
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

        file_content = await ctx.s3_get(origin_key)

        # 4. Resolve extractor and extract
        filename = (
            source_meta.get("document", {}).get("filename")
            or original_artifact.get("filename")
            or origin_key.split("/")[-1]
        )
        ext = _detect_ext(filename)

        extractor = await _resolve_extractor(ctx, ext)
        if extractor:
            extract_res = extractor.extract(file_content, filename)
        else:
            # Fallback to registry (handles unknown extensions)
            extract_res = ExtractorRegistry.extract(file_content, filename)

        extracted_text = extract_res.text.strip()

        if not extracted_text:
            raise ValueError(f"Failed to extract text from {filename}")

        # 5. Upload Artifact
        text_checksum = calculate_text_checksum(extracted_text)
        extracted_key = get_extracted_path(ctx.tenant_id, ctx.source_id, text_checksum)

        await ctx.s3_put(
            key=extracted_key,
            content=extracted_text.encode("utf-8"),
            content_type="text/plain",
        )

        source.meta = upsert_document_artifact(
            source_meta,
            "extracted",
            {
                "key": extracted_key,
                "content_type": "text/plain",
                "checksum": text_checksum,
                "size_bytes": len(extracted_text.encode("utf-8")),
                "extractor_kind": extract_res.kind,
            },
        )
        ctx.session.add(source)

        # 6. Complete
        metrics = {
            "word_count": len(extracted_text.split()),
            "char_count": len(extracted_text),
            "extractor": extract_res.kind,
            "checksum": text_checksum,
            "duration_sec": ctx.elapsed_sec,
            "file_size_bytes": len(file_content),
        }
        if extract_res.meta:
            metrics.update(extract_res.meta)

        await ctx.set_completed(metrics=metrics)
        await ctx.save_idempotency({
            "status": "completed",
            "extracted_key": extracted_key,
            "checksum": text_checksum,
            "extractor_kind": extract_res.kind,
        })
        await ctx.session.commit()

        return ExtractResult(
            source_id=source_id,
            extracted_key=extracted_key,
            extractor_kind=extract_res.kind,
            warnings=extract_res.warnings,
        )

    return run_stage(
        stage_name="extract",
        source_id=source_id,
        tenant_id=tenant_id,
        celery_task=self,
        execute_fn=_execute,
    )
