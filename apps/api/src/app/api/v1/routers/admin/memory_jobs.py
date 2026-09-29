"""Admin read and live-tail API for document-memory extraction jobs."""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.db import get_session_factory
from app.core.security import UserCtx
from app.models.document_memory_staging import DocumentMemorySnapshot, MemoryExtractionCandidate
from app.models.rag import RAGDocument
from app.schemas.runtime_events import RuntimeJournalEventResponse
from app.services.runtime_event_journal_service import RuntimeEventJournalService
from app.services.runtime_tail_event_bus import RuntimeTailSubscriber


router = APIRouter()
_SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
_JOURNAL_WIRE_FIELDS = {
    "type", "run_id", "event_id", "sequence", "occurred_at", "entity_type",
    "entity_id", "parent_entity_type", "parent_entity_id", "caused_by_event_id",
    "duration_ms",
}


def _event(row: object) -> dict[str, Any]:
    return RuntimeJournalEventResponse(
        id=getattr(row, "id"), run_id=getattr(row, "run_id"), sequence=getattr(row, "sequence"),
        event_type=getattr(row, "event_type"), occurred_at=getattr(row, "occurred_at"),
        entity_type=getattr(row, "entity_type"), entity_id=getattr(row, "entity_id"),
        parent_entity_type=getattr(row, "parent_entity_type"), parent_entity_id=getattr(row, "parent_entity_id"),
        caused_by_event_id=getattr(row, "caused_by_event_id"), duration_ms=getattr(row, "duration_ms"),
        payload=getattr(row, "payload") or {},
    ).model_dump(mode="json")


def _tail_event(message: dict[str, Any]) -> dict[str, Any] | None:
    if not all(key in message for key in ("event_id", "run_id", "sequence", "type", "occurred_at")):
        return None
    return RuntimeJournalEventResponse.model_validate({
        "id": message["event_id"], "run_id": message["run_id"], "sequence": message["sequence"],
        "event_type": message["type"], "occurred_at": message["occurred_at"],
        "entity_type": message.get("entity_type"), "entity_id": message.get("entity_id"),
        "parent_entity_type": message.get("parent_entity_type"), "parent_entity_id": message.get("parent_entity_id"),
        "caused_by_event_id": message.get("caused_by_event_id"), "duration_ms": message.get("duration_ms"),
        "payload": {key: value for key, value in message.items() if key not in _JOURNAL_WIRE_FIELDS},
    }).model_dump(mode="json")


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


def _job(snapshot: DocumentMemorySnapshot, document: RAGDocument | None, candidate_count: int) -> dict[str, Any]:
    return {
        "id": str(snapshot.id), "document_id": str(snapshot.document_id),
        "trace_run_id": str(snapshot.trace_run_id) if snapshot.trace_run_id else None,
        "status": snapshot.status, "candidate_count": candidate_count,
        "canonical_checksum": snapshot.canonical_checksum,
        "visibility_tenant_id": str(snapshot.visibility_tenant_id) if snapshot.visibility_tenant_id else None,
        "document_title": document.title if document else None,
        "document_filename": document.filename if document else None,
        "created_at": snapshot.created_at, "updated_at": snapshot.updated_at,
        "metrics": dict(snapshot.metrics or {}),
    }


@router.get("")
async def list_memory_jobs(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    rows = (await db.execute(
        select(DocumentMemorySnapshot, RAGDocument, func.count(MemoryExtractionCandidate.id).label("candidate_count"))
        .outerjoin(RAGDocument, RAGDocument.id == DocumentMemorySnapshot.document_id)
        .outerjoin(MemoryExtractionCandidate, MemoryExtractionCandidate.snapshot_id == DocumentMemorySnapshot.id)
        .group_by(DocumentMemorySnapshot.id, RAGDocument.id)
        .order_by(DocumentMemorySnapshot.updated_at.desc())
        .offset(offset).limit(limit)
    )).all()
    return [_job(snapshot, document, int(candidate_count)) for snapshot, document, candidate_count in rows]


@router.get("/{snapshot_id}")
async def get_memory_job(
    snapshot_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    snapshot = await db.get(DocumentMemorySnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Memory extraction job not found")
    document = await db.get(RAGDocument, snapshot.document_id)
    candidate_count = int(await db.scalar(select(func.count(MemoryExtractionCandidate.id)).where(
        MemoryExtractionCandidate.snapshot_id == snapshot.id,
    )) or 0)
    result = _job(snapshot, document, candidate_count)
    result["events"] = [
        _event(row) for row in await RuntimeEventJournalService(db).list_run_events(snapshot.trace_run_id)
    ] if snapshot.trace_run_id else []
    return result


@router.get("/{snapshot_id}/stream")
async def stream_memory_job(
    snapshot_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    snapshot = await db.get(DocumentMemorySnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Memory extraction job not found")
    if snapshot.trace_run_id is None:
        raise HTTPException(status_code=409, detail="Memory extraction trace has not started")
    run_id = snapshot.trace_run_id

    async def events() -> AsyncGenerator[str, None]:
        subscriber = RuntimeTailSubscriber(stream_key=str(run_id))
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        listener: asyncio.Task[None] | None = None
        emitted: set[str] = set()

        async def listen() -> None:
            async for message in subscriber.listen():
                await queue.put(message)

        try:
            await subscriber.subscribe()
            listener = asyncio.create_task(listen())
            async with get_session_factory()() as session:
                rows = await RuntimeEventJournalService(session).list_run_events(run_id)
            for row in rows:
                emitted.add(str(row.id))
                yield _sse("journal", _event(row))
            yield _sse("ready", {"snapshot_id": str(snapshot_id), "run_id": str(run_id)})
            while True:
                try:
                    message = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    async with get_session_factory()() as session:
                        current = await session.get(DocumentMemorySnapshot, snapshot_id)
                    if current is None or current.status in {"awaiting_review", "approved", "rejected", "skipped", "failed", "superseded"}:
                        yield _sse("done", {"snapshot_id": str(snapshot_id), "run_id": str(run_id)})
                        return
                    yield ": ping\n\n"
                    continue
                journal = _tail_event(message)
                if journal is None or str(journal["id"]) in emitted:
                    continue
                emitted.add(str(journal["id"]))
                yield _sse("journal", journal)
                if journal["event_type"] == "run_end":
                    yield _sse("done", {"snapshot_id": str(snapshot_id), "run_id": str(run_id)})
                    return
        finally:
            if listener is not None:
                listener.cancel()
                try:
                    await listener
                except asyncio.CancelledError:
                    pass
            await subscriber.unsubscribe()

    return StreamingResponse(events(), media_type="text/event-stream", headers=_SSE_HEADERS)
