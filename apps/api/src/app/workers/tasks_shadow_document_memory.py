"""Asynchronous shadow study of RAG-ready documents.

This workflow is deliberately isolated from legacy document memory and from
runtime recall.  It creates reviewable candidates only.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from celery import Task
from sqlalchemy import and_, or_, select

from app.adapters.s3_client import s3_manager
from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.core.di import get_llm_client
from app.models.document_memory_staging import DocumentMemoryExtractionAttempt, DocumentMemorySnapshot
from app.models.rag import RAGDocument
from app.models.rag_ingest import Source
from app.models.runtime_observability import RuntimeExecutionEvent
from app.runtime.memory.document_sections import split_canonical_sections
from app.runtime.memory.shadow_document_study import (
    SHADOW_STUDY_BATCH_SIZE,
    ShadowDocumentStudyAgent,
    ShadowDocumentStudyService,
)
from app.runtime.memory.shadow_memory_review import ShadowMemoryReviewService
from app.runtime.events import OrchestrationPhase, RuntimeEvent
from app.services.runtime_event_logger import (
    RuntimeEventJournalFactory,
    RuntimeLogContext,
    RuntimeLoggingLevel,
)
from app.storage.paths import calculate_text_checksum
from app.workers.session_factory import get_worker_session


def _source_id(index_results: Any) -> str:
    rows = index_results if isinstance(index_results, list) else [index_results]
    for row in rows:
        if isinstance(row, dict) and row.get("source_id"):
            return str(row["source_id"])
    return ""


def _trace_entity_id(snapshot_id: UUID, stage: str, *, cursor: int | None = None, kind: str, attempt_id: UUID | None = None) -> str:
    """Return a stable, single-part identity for one memory trace entity.

    The id is derived only from durable snapshot state.  Celery retries and
    handoffs therefore append to the same execution tree without correlating
    records by time, task name, or document text.
    """
    suffix = f":{cursor}" if cursor is not None else ""
    return str(uuid5(NAMESPACE_URL, f"document-memory/{attempt_id or snapshot_id}/{stage}{suffix}/{kind}"))


def _trace_logger(*, session, snapshot: DocumentMemorySnapshot, tenant_id: UUID | None):
    if snapshot.trace_run_id is None:
        snapshot.trace_run_id = uuid4()
    return RuntimeEventJournalFactory.create(
        context=RuntimeLogContext(
            run_id=snapshot.trace_run_id,
            level=RuntimeLoggingLevel.FULL,
            origin="worker",
            tenant_id=tenant_id,
            entity_type="run",
            entity_id=str(snapshot.trace_run_id),
            # The journal remains durable; this additionally publishes each
            # committed semantic event to the admin trace observer.
            stream_logs=True,
        ),
        session=session,
    )


async def _start_trace(*, session, logger, snapshot: DocumentMemorySnapshot, tenant_id: UUID | None) -> None:
    """Persist the root once, identified by the stored run id, not heuristics."""
    existing = (await session.execute(select(RuntimeExecutionEvent.id).where(
        RuntimeExecutionEvent.run_id == snapshot.trace_run_id,
        RuntimeExecutionEvent.event_type == "run_start",
    ).limit(1))).scalar_one_or_none()
    if existing is not None:
        return
    await logger.emit(
        RuntimeEvent.run_start(
            run_id=str(snapshot.trace_run_id),
            workflow="document_memory_extraction",
            snapshot_id=str(snapshot.id),
            attempt_id=str(snapshot.active_attempt_id) if snapshot.active_attempt_id else None,
            document_id=str(snapshot.document_id),
            tenant_id=str(tenant_id) if tenant_id else None,
            canonical_checksum=snapshot.canonical_checksum,
        ),
        phase=OrchestrationPhase.PIPELINE,
    )


async def _start_stage(*, logger, snapshot: DocumentMemorySnapshot, stage: str, cursor: int | None = None, task_id: str | None = None, retry: int = 0):
    stage_id = _trace_entity_id(snapshot.id, stage, cursor=cursor, kind="stage", attempt_id=snapshot.active_attempt_id)
    execution_id = _trace_entity_id(snapshot.id, stage, cursor=cursor, kind="execution", attempt_id=snapshot.active_attempt_id)
    await logger.emit(
        RuntimeEvent.orchestrator_start(
            orchestrator_id=stage_id,
            run_id=str(snapshot.trace_run_id),
            role="memory",
            workflow="document_memory_extraction",
            memory_stage=stage,
            snapshot_id=str(snapshot.id),
            attempt_id=str(snapshot.active_attempt_id) if snapshot.active_attempt_id else None,
            document_id=str(snapshot.document_id),
            cursor=cursor,
            celery_task_id=task_id,
            celery_retry=retry,
        ),
        phase=OrchestrationPhase.PIPELINE,
    )
    await logger.emit(
        RuntimeEvent.agent_start(
            agent_execution_id=execution_id,
            parent_entity_id=stage_id,
            parent_entity_type="orchestrator",
            agent_slug="document_memory_extractor",
            executor_name="Извлечение памяти из документа",
            task_title=stage,
            snapshot_id=str(snapshot.id),
            attempt_id=str(snapshot.active_attempt_id) if snapshot.active_attempt_id else None,
            document_id=str(snapshot.document_id),
            cursor=cursor,
        ),
        phase=OrchestrationPhase.AGENT,
    )
    return stage_id, execution_id


async def _end_stage(*, logger, snapshot: DocumentMemorySnapshot, stage: str, execution_id: str, status: str, cursor: int | None = None, **payload: Any) -> None:
    stage_id = _trace_entity_id(snapshot.id, stage, cursor=cursor, kind="stage", attempt_id=snapshot.active_attempt_id)
    await logger.emit(
        RuntimeEvent.agent_end(
            agent_execution_id=execution_id,
            parent_entity_id=stage_id,
            parent_entity_type="orchestrator",
            agent_slug="document_memory_extractor",
            status=status,
            **payload,
        ),
        phase=OrchestrationPhase.AGENT,
    )
    await logger.emit(
        RuntimeEvent.orchestrator_end(
            orchestrator_id=stage_id,
            run_id=str(snapshot.trace_run_id),
            status=status,
            memory_stage=stage,
            snapshot_id=str(snapshot.id),
            attempt_id=str(snapshot.active_attempt_id) if snapshot.active_attempt_id else None,
            document_id=str(snapshot.document_id),
            cursor=cursor,
            **payload,
        ),
        phase=OrchestrationPhase.PIPELINE,
    )


async def _end_trace(*, logger, snapshot: DocumentMemorySnapshot, status: str, **payload: Any) -> None:
    await logger.emit(
        RuntimeEvent.run_end(
            run_id=str(snapshot.trace_run_id),
            status=status,
            workflow="document_memory_extraction",
            snapshot_id=str(snapshot.id),
            attempt_id=str(snapshot.active_attempt_id) if snapshot.active_attempt_id else None,
            document_id=str(snapshot.document_id),
            snapshot_status=snapshot.status,
            **payload,
        ),
        phase=OrchestrationPhase.PIPELINE,
    )


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


def _attempt_message_matches(attempt, attempt_id: str | None, *, expected_cursor: int | None = None) -> bool:
    if attempt_id is None:
        if attempt.attempt_number != 1:
            return False
    elif str(attempt.id) != attempt_id:
        return False
    return expected_cursor is None or attempt.next_section == expected_cursor


async def dispatch_pending_shadow_studies(session) -> int:
    """Attempt rows are durable dispatch intents; delivery may repeat safely."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    rows = (await session.execute(select(DocumentMemoryExtractionAttempt, Source.tenant_id).join(
        DocumentMemorySnapshot, DocumentMemorySnapshot.active_attempt_id == DocumentMemoryExtractionAttempt.id,
    ).join(Source, Source.source_id == DocumentMemorySnapshot.document_id).where(
        DocumentMemorySnapshot.status == "studying",
        or_(DocumentMemoryExtractionAttempt.status == "queued",
            and_(DocumentMemoryExtractionAttempt.status == "studying",
                 DocumentMemoryExtractionAttempt.updated_at < cutoff)),
    ).limit(100))).all()
    dispatched = 0
    for attempt, source_tenant_id in rows:
        try:
            study_shadow_document_sections.delay(str(attempt.snapshot_id), str(source_tenant_id),
                                                 str(attempt.id), attempt.next_section)
            dispatched += 1
        except Exception:
            # The durable intent stays pending for the next beat after an outage.
            continue
    return dispatched


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
                document_id=source_uuid, checksum=checksum,
                visibility_tenant_id=None if document.scope == "global" else tenant_uuid,
            )
            snapshot, attempt = await service.lock_active_attempt(snapshot.id)
            snapshot.trace_run_id = attempt.trace_run_id
            logger = _trace_logger(session=session, snapshot=snapshot, tenant_id=tenant_uuid)
            await _start_trace(session=session, logger=logger, snapshot=snapshot, tenant_id=tenant_uuid)
            if snapshot.status in {"studying", "conflict_checking", "awaiting_review", "approved", "rejected", "skipped", "failed", "superseded"}:
                await logger.emit(
                    RuntimeEvent.status(
                        "memory_snapshot_cached", snapshot_id=str(snapshot.id),
                        document_id=str(snapshot.document_id), snapshot_status=snapshot.status,
                    ),
                    phase=OrchestrationPhase.PIPELINE,
                )
                await session.commit()
                return {"snapshot_id": str(snapshot.id), "status": snapshot.status, "cached": True}
            snapshot.status = "screening"
            stage_id, execution_id = await _start_stage(
                logger=logger, snapshot=snapshot, stage="screening",
                task_id=self.request.id, retry=self.request.retries,
            )
            document_payload = {
                "id": str(document.id), "title": document.title, "filename": document.filename,
                "scope": document.scope, "metadata": dict(canonical.get("metadata") or {}),
                "section_count": len(sections),
            }
            try:
                screening = await ShadowDocumentStudyAgent(session=session, llm_client=get_llm_client()).screen(
                    document=document_payload, sample_sections=sections[:2], tenant_id=tenant_uuid,
                    agent_execution_id=execution_id,
                    event_sink=lambda event: logger.emit(event, phase=OrchestrationPhase.AGENT),
                )
            except Exception as exc:
                await logger.emit(RuntimeEvent.error(
                    "Document-memory screening failed", recoverable=True, retryable=True,
                    parent_entity_type="agent_execution", parent_entity_id=execution_id,
                    snapshot_id=str(snapshot.id), document_id=str(snapshot.document_id),
                    memory_stage="screening", error_type=type(exc).__name__,
                ), phase=OrchestrationPhase.AGENT)
                await _end_stage(
                    logger=logger, snapshot=snapshot, stage="screening", execution_id=execution_id,
                    status="failed", error_type=type(exc).__name__,
                )
                if self.request.retries >= 3:
                    snapshot.status = "failed"
                    attempt.status = "failed"
                await session.commit()
                raise
            snapshot.metrics = {**dict(snapshot.metrics or {}), "screening": screening.model_dump()}
            await logger.emit(RuntimeEvent.status(
                "memory_screening_completed", entity_type="agent_execution", entity_id=execution_id,
                parent_entity_type="orchestrator", parent_entity_id=stage_id,
                decision=screening.decision, document_kind=screening.document_kind,
            ), phase=OrchestrationPhase.AGENT)
            if screening.decision == "skip":
                snapshot.status = "skipped"
                attempt.status = "completed"
                await _end_stage(
                    logger=logger, snapshot=snapshot, stage="screening", execution_id=execution_id,
                    status="completed", decision="skip", reason=screening.reason,
                )
                await _end_trace(logger=logger, snapshot=snapshot, status="completed", decision="skip")
                await session.commit()
                return {"snapshot_id": str(snapshot.id), "status": "skipped", "reason": screening.reason}
            snapshot.status = "studying"
            attempt.status = "studying"
            await _end_stage(
                logger=logger, snapshot=snapshot, stage="screening", execution_id=execution_id,
                status="completed", decision=screening.decision, reason=screening.reason,
            )
            await session.commit()
            study_shadow_document_sections.delay(str(snapshot.id), tenant_id, str(attempt.id), 0)
            return {"snapshot_id": str(snapshot.id), "status": "studying", "sections": len(sections)}

    return asyncio.run(execute())


@celery_app.task(
    queue="memory", bind=True, acks_late=True, reject_on_worker_lost=True,
    autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3},
)
def study_shadow_document_sections(self: Task, snapshot_id: str, tenant_id: str, attempt_id: str | None = None, expected_cursor: int = 0) -> dict[str, Any]:
    """Read one bounded canonical section batch and enqueue the next batch."""

    async def execute() -> dict[str, Any]:
        async with get_worker_session() as session:
            tenant_uuid, snapshot_uuid = UUID(tenant_id), UUID(snapshot_id)
            snapshot, attempt = await ShadowDocumentStudyService(session).lock_active_attempt(snapshot_uuid)
            if not _attempt_message_matches(attempt, attempt_id, expected_cursor=expected_cursor):
                return {"snapshot_id": snapshot_id, "status": "superseded_attempt", "cached": True}
            snapshot.trace_run_id = attempt.trace_run_id
            logger = _trace_logger(session=session, snapshot=snapshot, tenant_id=tenant_uuid)
            await _start_trace(session=session, logger=logger, snapshot=snapshot, tenant_id=tenant_uuid)
            if snapshot.status in {"conflict_checking", "awaiting_review", "approved", "rejected", "skipped", "superseded", "failed"}:
                return {"snapshot_id": snapshot_id, "status": snapshot.status, "cached": True}
            try:
                document, _source, canonical, sections, checksum = await _document_context(
                    session, source_id=snapshot.document_id, tenant_id=tenant_uuid,
                )
            except Exception as exc:
                await logger.emit(RuntimeEvent.error(
                    "Document-memory canonical artifact is unavailable", recoverable=True,
                    retryable=True, parent_entity_type="run",
                    parent_entity_id=str(snapshot.trace_run_id), snapshot_id=str(snapshot.id),
                    document_id=str(snapshot.document_id), memory_stage="load_canonical",
                    error_type=type(exc).__name__,
                ), phase=OrchestrationPhase.PIPELINE)
                if self.request.retries >= 3:
                    snapshot.status = "failed"
                    attempt.status = "failed"
                await session.commit()
                raise
            if checksum != snapshot.canonical_checksum:
                snapshot.status = "superseded"
                attempt.status = "superseded"
                await logger.emit(RuntimeEvent.status(
                    "memory_snapshot_superseded", snapshot_id=str(snapshot.id),
                    document_id=str(snapshot.document_id),
                ), phase=OrchestrationPhase.PIPELINE)
                await _end_trace(logger=logger, snapshot=snapshot, status="superseded")
                await session.commit()
                return {"snapshot_id": snapshot_id, "status": "superseded"}
            service = ShadowDocumentStudyService(session)
            attempt.status = "studying"
            cursor = max(0, int(attempt.next_section or 0))
            batch = sections[cursor:cursor + SHADOW_STUDY_BATCH_SIZE]
            if not batch:
                await logger.emit(RuntimeEvent.status(
                    "memory_study_complete_enqueuing_finalize", snapshot_id=str(snapshot.id),
                    document_id=str(snapshot.document_id), section_count=len(sections),
                ), phase=OrchestrationPhase.PIPELINE)
                snapshot.status = "conflict_checking"
                await service.finalize(snapshot, attempt)
                await session.commit()
                finalize_shadow_document_study.delay(snapshot_id, tenant_id, str(attempt.id))
                return {"snapshot_id": snapshot_id, "status": "finalizing"}
            stage_id, execution_id = await _start_stage(
                logger=logger, snapshot=snapshot, stage="study_sections", cursor=cursor,
                task_id=self.request.id, retry=self.request.retries,
            )
            projects_by_key, projects = await service.project_catalog()
            scopes_by_key, scopes = await service.scope_catalog()
            try:
                output = await ShadowDocumentStudyAgent(session=session, llm_client=get_llm_client()).study(
                    document={
                        "id": str(document.id), "title": document.title, "filename": document.filename,
                        "access_scope": document.scope,
                        "metadata": dict(canonical.get("metadata") or {}),
                    },
                    sections=batch,
                    candidate_ledger=await service.ledger(snapshot.id, attempt.id),
                    glossary=await service.glossary_context(), projects=projects,
                    scopes=scopes, tenant_id=tenant_uuid, correction_feedback=attempt.feedback,
                    agent_execution_id=execution_id,
                    event_sink=lambda event: logger.emit(event, phase=OrchestrationPhase.AGENT),
                )
            except Exception as exc:
                await logger.emit(RuntimeEvent.error(
                    "Document-memory section study failed", recoverable=True, retryable=True,
                    parent_entity_type="agent_execution", parent_entity_id=execution_id,
                    snapshot_id=str(snapshot.id), document_id=str(snapshot.document_id),
                    memory_stage="study_sections", cursor=cursor, error_type=type(exc).__name__,
                ), phase=OrchestrationPhase.AGENT)
                await _end_stage(
                    logger=logger, snapshot=snapshot, stage="study_sections", cursor=cursor,
                    execution_id=execution_id, status="failed", error_type=type(exc).__name__,
                )
                # A provider outage after one or more successful batches must
                # not strand those candidates in `extracted` forever. Expose
                # the partial snapshot for review once retries are exhausted.
                if self.request.retries >= 3:
                    service = ShadowDocumentStudyService(session)
                    await service.finalize(snapshot, attempt)
                    await session.commit()
                    finalize_shadow_document_study.delay(snapshot_id, tenant_id, str(attempt.id))
                await session.commit()
                raise
            active_snapshot = await session.scalar(select(DocumentMemorySnapshot).where(
                DocumentMemorySnapshot.id == snapshot.id,
            ).with_for_update().execution_options(populate_existing=True))
            if active_snapshot is None or active_snapshot.active_attempt_id != attempt.id:
                return {"snapshot_id": snapshot_id, "status": "superseded_attempt", "cached": True}
            counts = await service.persist_batch(
                snapshot=snapshot, attempt=attempt, items=output.items,
                section_ids={str(section["id"]) for section in batch}, projects_by_key=projects_by_key,
                scopes_by_key=scopes_by_key,
            )
            snapshot.status = "studying"
            snapshot.metrics = {**dict(snapshot.metrics or {}), "next_section": cursor + len(batch), "last_batch": counts}
            attempt.next_section = cursor + len(batch)
            await logger.emit(RuntimeEvent.status(
                "memory_batch_persisted", entity_type="agent_execution", entity_id=execution_id,
                parent_entity_type="orchestrator", parent_entity_id=stage_id,
                snapshot_id=str(snapshot.id), document_id=str(snapshot.document_id),
                cursor=cursor, section_ids=[str(section["id"]) for section in batch],
                section_count=len(batch), item_count=len(output.items), **counts,
            ), phase=OrchestrationPhase.AGENT)
            await _end_stage(
                logger=logger, snapshot=snapshot, stage="study_sections", cursor=cursor,
                execution_id=execution_id, status="completed", next_section=cursor + len(batch),
                section_count=len(batch), item_count=len(output.items), **counts,
            )
            await session.commit()
            study_shadow_document_sections.delay(snapshot_id, tenant_id, str(attempt.id), cursor + len(batch))
            return {"snapshot_id": snapshot_id, "status": "studying", "next_section": cursor + len(batch), **counts}

    return asyncio.run(execute())


@celery_app.task(
    queue="memory", bind=True, acks_late=True, reject_on_worker_lost=True,
    autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3},
)
def finalize_shadow_document_study(self: Task, snapshot_id: str, tenant_id: str, attempt_id: str | None = None) -> dict[str, Any]:
    """Move complete extracted candidates into the administrator review queue."""

    async def execute() -> dict[str, Any]:
        async with get_worker_session() as session:
            tenant_uuid = UUID(tenant_id)
            snapshot, attempt = await ShadowDocumentStudyService(session).lock_active_attempt(UUID(snapshot_id))
            if not _attempt_message_matches(attempt, attempt_id):
                return {"snapshot_id": snapshot_id, "status": "superseded_attempt", "cached": True}
            snapshot.trace_run_id = attempt.trace_run_id
            logger = _trace_logger(session=session, snapshot=snapshot, tenant_id=tenant_uuid)
            await _start_trace(session=session, logger=logger, snapshot=snapshot, tenant_id=tenant_uuid)
            if snapshot.status != "conflict_checking":
                return {"snapshot_id": snapshot_id, "status": snapshot.status, "cached": True}
            stage_id, execution_id = await _start_stage(
                logger=logger, snapshot=snapshot, stage="finalize_review",
                task_id=self.request.id, retry=self.request.retries,
            )
            service = ShadowDocumentStudyService(session)
            try:
                active_snapshot = await session.scalar(select(DocumentMemorySnapshot).where(
                    DocumentMemorySnapshot.id == snapshot.id,
                ).with_for_update().execution_options(populate_existing=True))
                if active_snapshot is None or active_snapshot.active_attempt_id != attempt.id:
                    return {"snapshot_id": snapshot_id, "status": "superseded_attempt", "cached": True}
                counts = await service.finalize(snapshot, attempt)
                attempt.status = "awaiting_review"
                await logger.emit(RuntimeEvent.status(
                    "memory_candidates_finalized", entity_type="agent_execution", entity_id=execution_id,
                    parent_entity_type="orchestrator", parent_entity_id=stage_id,
                    snapshot_id=str(snapshot.id), document_id=str(snapshot.document_id), **counts,
                ), phase=OrchestrationPhase.AGENT)
                conflict_counts = await ShadowMemoryReviewService(session).check_snapshot(
                    snapshot,
                    attempt_id=attempt.id,
                    agent_execution_id=execution_id,
                    event_sink=lambda event: logger.emit(event, phase=OrchestrationPhase.AGENT),
                )
            except Exception as exc:
                await logger.emit(RuntimeEvent.error(
                    "Document-memory finalization failed", recoverable=True, retryable=True,
                    parent_entity_type="agent_execution", parent_entity_id=execution_id,
                    snapshot_id=str(snapshot.id), document_id=str(snapshot.document_id),
                    memory_stage="finalize_review", error_type=type(exc).__name__,
                ), phase=OrchestrationPhase.AGENT)
                await _end_stage(
                    logger=logger, snapshot=snapshot, stage="finalize_review", execution_id=execution_id,
                    status="failed", error_type=type(exc).__name__,
                )
                await session.commit()
                raise
            attempt.status = "awaiting_review" if snapshot.status == "awaiting_review" else "completed"
            await logger.emit(RuntimeEvent.status(
                "memory_conflicts_checked", entity_type="agent_execution", entity_id=execution_id,
                parent_entity_type="orchestrator", parent_entity_id=stage_id,
                snapshot_id=str(snapshot.id), document_id=str(snapshot.document_id),
                snapshot_status=snapshot.status, **conflict_counts,
            ), phase=OrchestrationPhase.AGENT)
            await _end_stage(
                logger=logger, snapshot=snapshot, stage="finalize_review", execution_id=execution_id,
                status="completed", snapshot_status=snapshot.status, **counts, **conflict_counts,
            )
            await _end_trace(
                logger=logger, snapshot=snapshot, status="completed",
                **counts, **conflict_counts,
            )
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
            dispatched = await dispatch_pending_shadow_studies(session)
            rows = list((await session.execute(select(DocumentMemorySnapshot).where(
                DocumentMemorySnapshot.status == "conflict_checking",
            ).order_by(DocumentMemorySnapshot.updated_at).limit(100))).scalars().all())
            checked = 0
            for snapshot in rows:
                snapshot, attempt = await ShadowDocumentStudyService(session).lock_active_attempt(snapshot.id)
                if snapshot.status != "conflict_checking":
                    continue
                snapshot.trace_run_id = attempt.trace_run_id
                logger = _trace_logger(
                    session=session, snapshot=snapshot, tenant_id=snapshot.visibility_tenant_id,
                )
                await _start_trace(
                    session=session, logger=logger, snapshot=snapshot,
                    tenant_id=snapshot.visibility_tenant_id,
                )
                stage_id, execution_id = await _start_stage(
                    logger=logger, snapshot=snapshot, stage="reconcile_conflicts",
                    task_id=self.request.id, retry=self.request.retries,
                )
                try:
                    attempt = await ShadowDocumentStudyService(session).ensure_active_attempt(snapshot)
                    counts = await ShadowMemoryReviewService(session).check_snapshot(
                        snapshot,
                        attempt_id=attempt.id,
                        agent_execution_id=execution_id,
                        event_sink=lambda event: logger.emit(event, phase=OrchestrationPhase.AGENT),
                    )
                except Exception as exc:
                    await logger.emit(RuntimeEvent.error(
                        "Document-memory conflict reconciliation failed", recoverable=True,
                        retryable=False, parent_entity_type="agent_execution",
                        parent_entity_id=execution_id, snapshot_id=str(snapshot.id),
                        document_id=str(snapshot.document_id), memory_stage="reconcile_conflicts",
                        error_type=type(exc).__name__,
                    ), phase=OrchestrationPhase.AGENT)
                    await _end_stage(
                        logger=logger, snapshot=snapshot, stage="reconcile_conflicts",
                        execution_id=execution_id, status="failed", error_type=type(exc).__name__,
                    )
                    raise
                await _end_stage(
                    logger=logger, snapshot=snapshot, stage="reconcile_conflicts",
                    execution_id=execution_id, status="completed",
                    snapshot_status=snapshot.status, **counts,
                )
                if snapshot.status in {"awaiting_review", "approved", "rejected"}:
                    await _end_trace(
                        logger=logger, snapshot=snapshot, status="completed", **counts,
                    )
                attempt.status = "awaiting_review" if snapshot.status == "awaiting_review" else "completed"
                checked += 1
            await session.commit()
            return {"checked": checked, "dispatched": dispatched}
    return asyncio.run(execute())
