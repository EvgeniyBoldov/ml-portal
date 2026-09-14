from __future__ import annotations

import json
from typing import Any, Dict

from celery import Task
from sqlalchemy import select

from app.celery_app import app as celery_app
from app.models.project import Project
from app.models.rag import RAGDocument
from app.models.rag_ingest import Source
from app.models.memory import MemoryItemSource
from app.runtime.memory.document_memory import DocumentMemoryExtractor, DocumentMemoryService, split_canonical_sections
from app.storage.paths import calculate_text_checksum
from app.workers.tasks_rag_ingest.stage_context import IngestStageContext, run_stage
from app.workers.tasks_rag_ingest.stage_results import DocumentMemoryResult, NormalizeResult


def is_memory_trusted_source(meta: Any, *, document_scope: str) -> bool:
    """Global sources participate by default; local intake is explicit."""
    source_meta = meta if isinstance(meta, dict) else {}
    memory_meta = source_meta.get("memory")
    if isinstance(memory_meta, dict):
        for key in ("enabled", "trusted"):
            if memory_meta.get(key) is not None:
                return memory_meta.get(key) is True
    return document_scope == "global"


@celery_app.task(queue="memory", bind=True, acks_late=True, reject_on_worker_lost=True)
def extract_document_memory(
    self: Task, normalize_result: Dict[str, Any], tenant_id: str, force: bool = False,
) -> Dict[str, Any]:
    """Extract source-backed semantic memory without blocking RAG readiness."""
    previous = NormalizeResult.from_dict(normalize_result)

    async def _execute(ctx: IngestStageContext) -> DocumentMemoryResult:
        await ctx.set_processing()
        canonical_key = previous.canonical_key
        cached = await ctx.check_idempotency(s3_key_field="canonical_key")
        if cached and not force:
            await ctx.set_completed(metrics={"cached": True, **dict(cached.get("metrics") or {})})
            await ctx.session.commit()
            return DocumentMemoryResult(source_id=previous.source_id)

        source = (await ctx.session.execute(select(Source).where(
            Source.source_id == ctx.source_id,
            Source.tenant_id == ctx.tenant_id,
        ))).scalar_one_or_none()
        if source is None:
            raise ValueError(f"Source {ctx.source_id} not found for tenant")
        document = (await ctx.session.execute(select(RAGDocument).where(
            RAGDocument.id == ctx.source_id,
        ))).scalar_one_or_none()
        if document is None:
            raise ValueError(f"RAG document {ctx.source_id} not found")
        if not is_memory_trusted_source(source.meta, document_scope=str(document.scope or "local")):
            metrics = {"skipped": "untrusted_source"}
            await ctx.set_completed(metrics=metrics)
            await ctx.save_idempotency({"status": "completed", "canonical_key": canonical_key, "metrics": metrics})
            await ctx.session.commit()
            return DocumentMemoryResult(source_id=previous.source_id)

        canonical = json.loads((await ctx.s3_get(canonical_key)).decode("utf-8"))
        text = str(canonical.get("text") or "")
        sections = split_canonical_sections(text)
        projects = list((await ctx.session.execute(select(Project).where(Project.is_active.is_(True)))).scalars().all())
        document_meta = dict(canonical.get("metadata") or {})
        from app.core.di import get_llm_client
        extractor = DocumentMemoryExtractor(session=ctx.session, llm_client=get_llm_client())
        candidates = await extractor.extract(
            document={
                "id": str(ctx.source_id),
                "title": document_meta.get("title") or document_meta.get("filename") or str(ctx.source_id),
                "filename": document_meta.get("filename"),
                "project_keys": list((source.meta or {}).get("memory", {}).get("project_keys") or []),
            },
            sections=sections,
            projects=[{"key": project.key, "name": project.name, "aliases": list(project.aliases or [])} for project in projects],
            tenant_id=ctx.tenant_id,
        )
        checksum = calculate_text_checksum(text)
        counts = await DocumentMemoryService(ctx.session).apply(
            document_id=ctx.source_id,
            canonical_checksum=checksum,
            candidates=candidates,
            sections=sections,
            tenant_id=document.tenant_id,
            document_scope=str(document.scope or "local"),
        )
        metrics = {
            "sections": len(sections), "candidates": len(candidates),
            # A successful extraction, including one that finds no durable
            # normative knowledge, has evaluated the current strict contract.
            "typed_content_contract": True,
            "entity_graph_contract": True,
            "rejected_contracts": dict(extractor.rejection_counts),
            **counts,
        }
        await ctx.set_completed(metrics=metrics)
        await ctx.save_idempotency({"status": "completed", "canonical_key": canonical_key, "metrics": metrics})
        await ctx.session.commit()
        item_ids = [str(row[0]) for row in (await ctx.session.execute(
            select(MemoryItemSource.memory_item_id).where(
                MemoryItemSource.document_id == ctx.source_id,
                MemoryItemSource.canonical_checksum == checksum,
            )
        )).all()]
        if item_ids:
            from app.workers.tasks_memory import index_memory_items
            index_memory_items.delay(item_ids)
        return DocumentMemoryResult(source_id=previous.source_id, **counts)

    return run_stage(
        stage_name="memory.extract",
        source_id=previous.source_id,
        tenant_id=tenant_id,
        celery_task=self,
        execute_fn=_execute,
    )
