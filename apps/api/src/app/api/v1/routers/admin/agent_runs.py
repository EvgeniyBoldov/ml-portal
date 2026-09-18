"""Admin read model for persisted, per-agent runtime journals."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.runtime_events import RuntimeJournalEventResponse
from app.services.runtime_event_journal_service import RuntimeEventJournalService
from app.models.agent import Agent

router = APIRouter()


def _event(row: object) -> RuntimeJournalEventResponse:
    return RuntimeJournalEventResponse(
        id=getattr(row, "id"), run_id=getattr(row, "run_id"), sequence=getattr(row, "sequence"),
        event_type=getattr(row, "event_type"), occurred_at=getattr(row, "occurred_at"),
        entity_type=getattr(row, "entity_type"), entity_id=getattr(row, "entity_id"),
        parent_entity_type=getattr(row, "parent_entity_type"), parent_entity_id=getattr(row, "parent_entity_id"),
        caused_by_event_id=getattr(row, "caused_by_event_id"), duration_ms=getattr(row, "duration_ms"),
        payload=getattr(row, "payload") or {},
    )


@router.get("")
async def list_agent_runs(
    tenant_id: UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    rows = await RuntimeEventJournalService(db).list_agent_executions(
        tenant_id=tenant_id, limit=limit, offset=offset,
    )
    slugs = {str((row.payload or {}).get("agent_slug") or "") for row in rows}
    agents = (await db.execute(select(Agent).where(Agent.slug.in_(slugs - {""})))).scalars().all() if slugs - {""} else []
    by_slug = {agent.slug: agent for agent in agents}
    return [{
        "agent_execution_id": row.entity_id,
        "run_id": str(row.run_id),
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "user_id": str(row.user_id) if row.user_id else None,
        "agent_id": str(by_slug[slug].id) if (slug := str((row.payload or {}).get("agent_slug") or "")) in by_slug else None,
        "agent_name": by_slug[slug].name if slug in by_slug else None,
        "agent_slug": slug or None,
        "task_title": (row.payload or {}).get("task_title"),
        "logging_level": row.logging_level,
        "started_at": row.occurred_at,
    } for row in rows]


@router.get("/{agent_execution_id}")
async def get_agent_run(
    agent_execution_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    events = await RuntimeEventJournalService(db).list_agent_execution_events(str(agent_execution_id))
    if not events:
        raise HTTPException(status_code=404, detail="Agent run not found")
    root = next((row for row in events if row.entity_type == "agent_execution"), events[0])
    slug = str((root.payload or {}).get("agent_slug") or "")
    agent = await db.scalar(select(Agent).where(Agent.slug == slug)) if slug else None
    return {
        "agent_execution_id": str(agent_execution_id),
        "run_id": str(root.run_id),
        "agent_id": str(agent.id) if agent else None,
        "agent_name": agent.name if agent else None,
        "agent_slug": slug or None,
        "events": [_event(row).model_dump(mode="json") for row in events],
    }
