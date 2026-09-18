"""Asynchronous shadow study of RAG-ready documents.

This workflow is deliberately isolated from legacy document memory and from
runtime recall.  It creates reviewable candidates only.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from celery import Task
from sqlalchemy import select

from app.adapters.s3_client import s3_manager
from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.core.di import get_llm_client
from app.models.document_memory_staging import DocumentMemorySnapshot
from app.models.rag import RAGDocument
from app.models.rag_ingest import Source
from app.runtime.memory.document_memory import split_canonical_sections
from app.runtime.memory.shadow_document_study import (
    SHADOW_STUDY_BATCH_SIZE,
    ShadowDocumentStudyAgent,
    ShadowDocumentStudyService,
)
from app.runtime.memory.shadow_memory_review import ShadowMemoryReviewService
from app.storage.paths import calculate_text_checksum
from app.workers.session_factory import get_worker_session


def _source_id(index_results: Any) -> str:
    rows = index_results if isinstance(index_results, list) else [index_results]
    for row in rows:
        if isinstance(row, dict) and row.get("source_id"):
            return str(row["source_id"])
    return ""


async def _document_context(session, *, source_id: UUID, tenant_id: UUID) -> tuple[RAGDocument, Source, dict[str, Any], list[dict[str, Any]], str]:
    source = (await session.execute(select(Source).where(
        Source.source_id == source_id, Source.tenant_id == tenant_id,
    ))).scalar_one_or_none()
    document = (await session.execute(select(RAGDocument).where(
        RAGDocument.id == source_id,
    ))).scalar_one_or_none()
    if source is None or document is None or not document.s3_key_processed:
        raise ValueError("RAG-ready document source or canonical artifact is unavailable")
    payload = await s3_manager.get_object(get_settings().S3_BUCKET_RAG, document.s3_key_processed)
    canonical = json.loads(payload.decode("utf-8"))
    text = str(canonical.get("text") or "")
    if not text.strip():
        raise ValueError("Canonical document is empty")
    return document, source, canonical, split_canonical_sections(text), calculate_text_checksum(text)


@celery_app.task(
    queue="memory", bind=True, acks_late=True, reject_on_worker_lost=True,
    autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3},
)
def shadow_study_rag_document(self: Task, index_results: Any, tenant_id: str) -> dict[str, Any]:
    """Create a snapshot and run screening after every successful RAG index group."""
    source_id = _source_id(index_results)
    if not source_id:
        raise ValueError("RAG index result does not contain source_id")

    async def execute() -> dict[str, Any]:
        async with get_worker_session() as session:
            tenant_uuid, source_uuid = UUID(tenant_id), UUID(source_id)
            document, _source, canonical, sections, checksum = await _document_context(
                session, source_id=source_uuid, tenant_id=tenant_uuid,
            )
            service = ShadowDocumentStudyService(session)
            snapshot = await service.get_or_create_snapshot(
                document_id=source_uuid, checksum=checksum, visibility_tenant_id=tenant_uuid,
            )
            if snapshot.status in {"studying", "conflict_checking", "awaiting_review", "approved", "skipped"}:
                await session.commit()
                return {"snapshot_id": str(snapshot.id), "status": snapshot.status, "cached": True}
            snapshot.status = "screening"
            document_payload = {
                "id": str(document.id), "title": document.title, "filename": document.filename,
                "scope": document.scope, "metadata": dict(canonical.get("metadata") or {}),
                "section_count": len(sections),
            }
            screening = await ShadowDocumentStudyAgent(session=session, llm_client=get_llm_client()).screen(
                document=document_payload, sample_sections=sections[:2], tenant_id=tenant_uuid,
            )
            snapshot.metrics = {**dict(snapshot.metrics or {}), "screening": screening.model_dump()}
            if screening.decision == "skip":
                snapshot.status = "skipped"
                await session.commit()
                return {"snapshot_id": str(snapshot.id), "status": "skipped", "reason": screening.reason}
            snapshot.status = "studying"
            await session.commit()
            study_shadow_document_sections.delay(str(snapshot.id), tenant_id)
            return {"snapshot_id": str(snapshot.id), "status": "studying", "sections": len(sections)}

    return asyncio.run(execute())


@celery_app.task(
    queue="memory", bind=True, acks_late=True, reject_on_worker_lost=True,
    autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3},
)
def study_shadow_document_sections(self: Task, snapshot_id: str, tenant_id: str) -> dict[str, Any]:
    """Read one bounded canonical section batch and enqueue the next batch."""

    async def execute() -> dict[str, Any]:
        async with get_worker_session() as session:
            tenant_uuid, snapshot_uuid = UUID(tenant_id), UUID(snapshot_id)
            snapshot = await session.get(DocumentMemorySnapshot, snapshot_uuid)
            if snapshot is None:
                raise ValueError("Shadow study snapshot not found")
            if snapshot.status in {"conflict_checking", "awaiting_review", "approved", "rejected", "skipped", "superseded", "failed"}:
                return {"snapshot_id": snapshot_id, "status": snapshot.status, "cached": True}
            document, _source, canonical, sections, checksum = await _document_context(
                session, source_id=snapshot.document_id, tenant_id=tenant_uuid,
            )
            if checksum != snapshot.canonical_checksum:
                snapshot.status = "superseded"
                await session.commit()
                return {"snapshot_id": snapshot_id, "status": "superseded"}
            service = ShadowDocumentStudyService(session)
            cursor = max(0, int(dict(snapshot.metrics or {}).get("next_section") or 0))
            batch = sections[cursor:cursor + SHADOW_STUDY_BATCH_SIZE]
            if not batch:
                finalize_shadow_document_study.delay(snapshot_id, tenant_id)
                return {"snapshot_id": snapshot_id, "status": "finalizing"}
            projects_by_key, projects = await service.project_catalog()
            output = await ShadowDocumentStudyAgent(session=session, llm_client=get_llm_client()).study(
                document={
                    "id": str(document.id), "title": document.title, "filename": document.filename,
                    "metadata": dict(canonical.get("metadata") or {}),
                },
                sections=batch,
                candidate_ledger=await service.ledger(snapshot.id),
                glossary=await service.glossary_context(visibility_tenant_id=snapshot.visibility_tenant_id), projects=projects, tenant_id=tenant_uuid,
            )
            counts = await service.persist_batch(
                snapshot=snapshot, items=output.items,
                section_ids={str(section["id"]) for section in batch}, projects_by_key=projects_by_key,
            )
            snapshot.status = "studying"
            snapshot.metrics = {**dict(snapshot.metrics or {}), "next_section": cursor + len(batch), "last_batch": counts}
            await session.commit()
            study_shadow_document_sections.delay(snapshot_id, tenant_id)
            return {"snapshot_id": snapshot_id, "status": "studying", "next_section": cursor + len(batch), **counts}

    return asyncio.run(execute())


@celery_app.task(
    queue="memory", bind=True, acks_late=True, reject_on_worker_lost=True,
    autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3},
)
def finalize_shadow_document_study(self: Task, snapshot_id: str, tenant_id: str) -> dict[str, Any]:
    """Move complete extracted candidates into the administrator review queue."""

    async def execute() -> dict[str, Any]:
        async with get_worker_session() as session:
            snapshot = await session.get(DocumentMemorySnapshot, UUID(snapshot_id))
            if snapshot is None:
                raise ValueError("Shadow study snapshot not found")
            if snapshot.status in {"awaiting_review", "approved", "rejected"}:
                return {"snapshot_id": snapshot_id, "status": snapshot.status, "cached": True}
            service = ShadowDocumentStudyService(session)
            counts = await service.finalize(snapshot)
            conflict_counts = await ShadowMemoryReviewService(session).check_snapshot(snapshot)
            await session.commit()
            return {"snapshot_id": snapshot_id, "status": snapshot.status, **counts, **conflict_counts}

    return asyncio.run(execute())


@celery_app.task(queue="maintenance.default", bind=True, acks_late=True, reject_on_worker_lost=True)
def reconcile_shadow_memory_conflicts(self: Task) -> dict[str, int]:
    """Retry bounded review for staged snapshots left awaiting a decision.

    New snapshots are checked immediately; this task is a safety net for
    interrupted finalization and makes the queue observable to Celery beat.
    """
    async def execute() -> dict[str, int]:
        async with get_worker_session() as session:
            rows = list((await session.execute(select(DocumentMemorySnapshot).where(
                DocumentMemorySnapshot.status == "conflict_checking",
            ).order_by(DocumentMemorySnapshot.updated_at).limit(100))).scalars().all())
            checked = 0
            for snapshot in rows:
                await ShadowMemoryReviewService(session).check_snapshot(snapshot)
                checked += 1
            await session.commit()
            return {"checked": checked}
    return asyncio.run(execute())
