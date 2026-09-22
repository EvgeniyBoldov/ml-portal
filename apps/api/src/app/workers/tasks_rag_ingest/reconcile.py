"""Recovery loop for committed-but-not-yet-published ingest commands."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from celery import Task
from sqlalchemy import select

from app.celery_app import app as celery_app
from app.models.rag_ingest import RAGIngestOutbox, RAGIngestStageOutbox
from app.workers.session_factory import get_worker_session


async def _pending_outbox_ids(limit: int) -> list[str]:
    async with get_worker_session() as session:
        rows = await session.execute(
            select(RAGIngestOutbox.id)
            .where(
                RAGIngestOutbox.status == "pending",
                RAGIngestOutbox.available_at <= datetime.now(timezone.utc),
            )
            .order_by(RAGIngestOutbox.created_at)
            .limit(limit)
        )
        return [str(item) for item in rows.scalars().all()]


async def _pending_stage_outbox_ids(limit: int) -> list[str]:
    async with get_worker_session() as session:
        rows = await session.execute(
            select(RAGIngestStageOutbox.id)
            .where(
                RAGIngestStageOutbox.status == "pending",
                RAGIngestStageOutbox.available_at <= datetime.now(timezone.utc),
            )
            .order_by(RAGIngestStageOutbox.created_at)
            .limit(limit)
        )
        return [str(item) for item in rows.scalars().all()]


@celery_app.task(queue="maintenance.default", bind=True)
def reconcile_rag_ingest_outbox(self: Task, limit: int = 100) -> int:
    from app.workers.tasks_rag_ingest.dispatch import (
        dispatch_rag_ingest_outbox, dispatch_rag_ingest_stage_outbox,
    )
    ids = asyncio.run(_pending_outbox_ids(limit))
    for outbox_id in ids:
        dispatch_rag_ingest_outbox.delay(outbox_id)
    stage_ids = asyncio.run(_pending_stage_outbox_ids(limit))
    for outbox_id in stage_ids:
        dispatch_rag_ingest_stage_outbox.delay(outbox_id)
    return len(ids) + len(stage_ids)
