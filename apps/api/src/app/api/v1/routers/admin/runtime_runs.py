"""Admin read model for complete persisted chat runtime traces."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.runtime_observability import RuntimeExecutionEvent
from app.schemas.runtime_events import RuntimeJournalEventResponse

router = APIRouter()


def _event(row: RuntimeExecutionEvent) -> dict:
    return RuntimeJournalEventResponse(
        id=row.id, run_id=row.run_id, sequence=row.sequence, event_type=row.event_type,
        occurred_at=row.occurred_at, entity_type=row.entity_type, entity_id=row.entity_id,
        parent_entity_type=row.parent_entity_type, parent_entity_id=row.parent_entity_id,
        caused_by_event_id=row.caused_by_event_id, duration_ms=row.duration_ms,
        payload=row.payload or {},
    ).model_dump(mode="json")


@router.get("")
async def list_chat_runtime_runs(
    tenant_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
) -> list[dict]:
    filters = (
        RuntimeExecutionEvent.entity_type == "run",
        RuntimeExecutionEvent.event_type == "run_start",
        RuntimeExecutionEvent.origin == "chat",
    )
    ranked = select(
        RuntimeExecutionEvent.id.label("event_id"),
        func.row_number().over(
            partition_by=RuntimeExecutionEvent.run_id,
            order_by=(RuntimeExecutionEvent.occurred_at.desc(), RuntimeExecutionEvent.sequence.desc()),
        ).label("run_rank"),
    ).where(*filters)
    if tenant_id is not None:
        ranked = ranked.where(RuntimeExecutionEvent.tenant_id == tenant_id)
    ranked = ranked.subquery()
    stmt = (
        select(RuntimeExecutionEvent)
        .join(ranked, RuntimeExecutionEvent.id == ranked.c.event_id)
        .where(ranked.c.run_rank == 1)
        .order_by(RuntimeExecutionEvent.occurred_at.desc())
        .offset(offset)
        .limit(limit)
    )
    runs = (await db.execute(stmt)).scalars().all()
    return [{
        "run_id": str(row.run_id),
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "user_id": str(row.user_id) if row.user_id else None,
        "chat_id": str(row.chat_id) if row.chat_id else None,
        "started_at": row.occurred_at,
        "logging_level": row.logging_level,
    } for row in runs]


@router.get("/{run_id}")
async def get_chat_runtime_run(
    run_id: UUID,
    after_sequence: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
) -> dict:
    root_exists = await db.scalar(select(RuntimeExecutionEvent.id).where(
        RuntimeExecutionEvent.run_id == run_id,
        RuntimeExecutionEvent.entity_type == "run",
        RuntimeExecutionEvent.event_type == "run_start",
        RuntimeExecutionEvent.origin == "chat",
    ).limit(1))
    if root_exists is None:
        raise HTTPException(status_code=404, detail="Chat runtime trace not found")
    stmt = select(RuntimeExecutionEvent).where(
        RuntimeExecutionEvent.run_id == run_id,
        RuntimeExecutionEvent.sequence > after_sequence,
    ).order_by(RuntimeExecutionEvent.sequence).limit(limit + 1)
    rows = list((await db.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "run_id": str(run_id),
        "events": [_event(row) for row in page],
        "next_after_sequence": page[-1].sequence if page and has_more else None,
        "has_more": has_more,
    }
