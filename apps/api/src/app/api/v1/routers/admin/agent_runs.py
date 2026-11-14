"""Admin read model for persisted, per-agent runtime journals."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.runtime_events import RuntimeJournalEventResponse
from app.services.runtime_event_journal_service import RuntimeEventJournalService
from app.models.agent import Agent
from app.models.agent_version import AgentVersion
from app.models.runtime_observability import RuntimeExecutionEvent
from app.models.user import Users

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
    user_ids = {row.user_id for row in rows if row.user_id}
    users = (await db.execute(select(Users).where(Users.id.in_(user_ids)))).scalars().all() if user_ids else []
    user_name_by_id = {user.id: user.full_name or user.login for user in users}
    execution_ids = [row.entity_id for row in rows if row.entity_id]
    current_version_ids = [agent.current_version_id for agent in agents if agent.current_version_id]
    event_version_ids: set[UUID] = set()
    for row in rows:
        value = (row.payload or {}).get("agent_version_id")
        if value:
            try:
                event_version_ids.add(UUID(str(value)))
            except ValueError:
                continue
    version_ids = {*current_version_ids, *event_version_ids}
    versions = (await db.execute(select(AgentVersion).where(AgentVersion.id.in_(version_ids)))).scalars().all() if version_ids else []
    mission_by_version_id = {str(version.id): version.mission for version in versions}
    mission_by_agent_id = {
        str(agent.id): mission_by_version_id.get(str(agent.current_version_id))
        for agent in agents if agent.current_version_id
    }
    related_events = (await db.execute(select(RuntimeExecutionEvent).where(
        RuntimeExecutionEvent.run_id.in_({row.run_id for row in rows}),
        RuntimeExecutionEvent.event_type.in_(["agent_end", "status"]),
        or_(RuntimeExecutionEvent.entity_id.in_(execution_ids), RuntimeExecutionEvent.parent_entity_id.in_(execution_ids)),
    ).order_by(RuntimeExecutionEvent.sequence))).scalars().all() if rows else []
    events_by_execution: dict[str, list[RuntimeExecutionEvent]] = {}
    for event in related_events:
        owner_id = str(event.entity_id or "")
        if owner_id not in execution_ids:
            owner_id = str(event.parent_entity_id or "")
        if owner_id in execution_ids:
            events_by_execution.setdefault(owner_id, []).append(event)

    def task_title(row: RuntimeExecutionEvent, agent: Agent | None) -> str | None:
        payload = row.payload or {}
        snapshot = payload.get("context_snapshot") or {}
        title = payload.get("task_title") or (snapshot.get("task_title") if isinstance(snapshot, dict) else None)
        if title:
            return str(title)
        if row.origin == "shadow":
            mission = mission_by_version_id.get(str(payload.get("agent_version_id") or ""))
            if not mission and agent:
                mission = mission_by_agent_id.get(str(agent.id))
            if mission:
                return str(mission)
        for event in events_by_execution.get(str(row.entity_id), []):
            event_payload = event.payload or {}
            snapshot = event_payload.get("context_snapshot") or {}
            inputs = snapshot.get("inputs") or {} if isinstance(snapshot, dict) else {}
            if not isinstance(inputs, dict):
                continue
            title = inputs.get("intent") or inputs.get("goal") or inputs.get("task_title")
            if title:
                return str(title)
        return None

    return [{
        "agent_execution_id": row.entity_id,
        "run_id": str(row.run_id),
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "user_id": str(row.user_id) if row.user_id else None,
        "agent_id": str(by_slug[slug].id) if (slug := str((row.payload or {}).get("agent_slug") or "")) in by_slug else None,
        "agent_name": by_slug[slug].name if slug in by_slug else None,
        "agent_slug": slug or None,
        "task_title": task_title(row, by_slug.get(str((row.payload or {}).get("agent_slug") or ""))),
        "status": next((str((event.payload or {}).get("status")) for event in reversed(events_by_execution.get(str(row.entity_id), [])) if event.event_type == "agent_end" and (event.payload or {}).get("status")), "running"),
        "agent_type": "shadow" if row.origin == "shadow" else "regular",
        "user_name": user_name_by_id.get(row.user_id),
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
