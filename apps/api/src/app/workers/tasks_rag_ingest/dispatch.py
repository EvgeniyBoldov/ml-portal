"""Transactional-outbox dispatcher for RAG ingest pipelines."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

from celery import Task
from sqlalchemy import select

from app.celery_app import app as celery_app
from app.models.rag_ingest import RAGIngestOutbox, RAGIngestRun
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager
from app.workers.session_factory import get_worker_session


async def _dispatch(outbox_id: str) -> str | None:
    async with get_worker_session() as session:
        result = await session.execute(
            select(RAGIngestOutbox, RAGIngestRun)
            .join(RAGIngestRun, RAGIngestRun.id == RAGIngestOutbox.run_id)
            .where(RAGIngestOutbox.id == UUID(outbox_id))
            .with_for_update(skip_locked=True)
        )
        row = result.first()
        if not row:
            return None
        outbox, run = row
        if outbox.status == "dispatched" or run.status in {"cancelled", "failed", "completed"}:
            return outbox.celery_task_id

        # A newer generation wins.  We never dispatch obsolete queued work.
        from app.models.rag import RAGDocument
        document = (await session.execute(select(RAGDocument).where(RAGDocument.id == run.doc_id))).scalar_one()
        if int(document.ingest_generation or 0) != run.generation:
            outbox.status = "cancelled"
            run.status = "cancelled"
            await session.commit()
            return None

        payload = dict(outbox.payload or {})
        payload.setdefault("source_id", str(run.doc_id))
        from app.models.rag_ingest import RAGIngestStageOutbox
        if run.resume_stage == "embed":
            stage_key = f"embed.{payload['model_alias']}"
        else:
            stage_key = "extract"
        stage_command = RAGIngestStageOutbox(
            run_id=run.id,
            stage_key=stage_key,
            payload=payload,
            status="pending",
        )
        session.add(stage_command)
        now = datetime.now(timezone.utc)
        outbox.status = "dispatched"
        outbox.attempts = int(outbox.attempts or 0) + 1
        outbox.dispatched_at = now
        run.status = "running"
        run.started_at = run.started_at or now
        await session.commit()
        # This is deliberately after commit. A periodic reconciler covers a
        # broker outage between the commit and this best-effort publication.
        dispatch_rag_ingest_stage_outbox.delay(str(stage_command.id))
        return str(stage_command.id)


@celery_app.task(queue="maintenance.default", bind=True, acks_late=True, reject_on_worker_lost=True)
def dispatch_rag_ingest_outbox(self: Task, outbox_id: str) -> str | None:
    return asyncio.run(_dispatch(outbox_id))


async def _dispatch_stage(outbox_id: str) -> str | None:
    from app.models.rag_ingest import RAGIngestStageOutbox
    async with get_worker_session() as session:
        row = (await session.execute(
            select(RAGIngestStageOutbox, RAGIngestRun)
            .join(RAGIngestRun, RAGIngestRun.id == RAGIngestStageOutbox.run_id)
            .where(RAGIngestStageOutbox.id == UUID(outbox_id))
            .with_for_update(skip_locked=True)
        )).first()
        if not row:
            return None
        command, run = row
        if command.status == "dispatched" or (
            run.status not in {"queued", "running"} and not (command.stage_key == "shadow" and run.status == "completed")
        ):
            return command.celery_task_id

        from app.models.rag import RAGDocument
        document = (await session.execute(select(RAGDocument).where(RAGDocument.id == run.doc_id))).scalar_one()
        if int(document.ingest_generation or 0) != run.generation:
            command.status = "cancelled"
            run.status = "cancelled"
            await session.commit()
            return None

        from app.workers.tasks_rag_ingest import (
            extract_document, normalize_document, chunk_document, embed_chunks_model, index_model,
        )
        payload = command.payload or {}
        stage = command.stage_key
        if stage == "extract":
            task_fn = extract_document
            task_args = [str(run.doc_id), str(run.tenant_id), str(run.id), run.generation]
        elif stage == "normalize":
            task_fn = normalize_document
            task_args = [payload, str(run.tenant_id), str(run.id), run.generation]
        elif stage == "chunk":
            task_fn = chunk_document
            task_args = [payload, str(run.tenant_id), str(run.id), run.generation]
        elif stage.startswith("embed."):
            task_fn = embed_chunks_model
            task_args = [payload, str(run.tenant_id), stage.split(".", 1)[1], str(run.id), run.generation]
        elif stage.startswith("index."):
            task_fn = index_model
            task_args = [payload, str(run.tenant_id), str(run.id), run.generation]
        elif stage == "shadow":
            from app.workers.tasks_shadow_document_memory import shadow_study_rag_document
            task_fn = shadow_study_rag_document
            task_args = [[payload], str(run.tenant_id)]
        else:
            raise ValueError(f"Unsupported RAG ingest stage command: {stage}")
        task_id = str(uuid4())
        command.status = "dispatched"
        command.celery_task_id = task_id
        command.attempts = int(command.attempts or 0) + 1
        command.dispatched_at = datetime.now(timezone.utc)
        # Persist the task id while it is queued, so stop/retry controls can
        # operate before the worker starts the task. The stage itself will
        # publish processing/completed/failed events with metrics.
        if stage != "shadow":
            manager = RAGStatusManager(session, AsyncRepositoryFactory(session, run.tenant_id))
            node_type, node_key = manager._split_stage_name(stage)
            node = await manager.status_repo.get_node(run.doc_id, node_type, node_key)
            if node:
                node.status = "queued"
                node.celery_task_id = task_id
                node.updated_at = datetime.now(timezone.utc)
                await session.flush()
        await session.commit()
        try:
            task_fn.apply_async(args=task_args, task_id=task_id)
        except Exception as exc:
            # The command is durable; make it eligible for recovery again.
            command.status = "pending"
            command.last_error = f"broker publish failed: {type(exc).__name__}: {exc}"[:500]
            command.celery_task_id = None
            await session.commit()
            raise
        return task_id


@celery_app.task(queue="maintenance.default", bind=True, acks_late=True, reject_on_worker_lost=True)
def dispatch_rag_ingest_stage_outbox(self: Task, outbox_id: str) -> str | None:
    return asyncio.run(_dispatch_stage(outbox_id))
