"""Provider-neutral authenticated API for external conversational adapters."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, db_uow, get_bearer_user, resolve_active_user_tenant_ids
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.security import UserCtx
from app.schemas.durable_runtime import (
    MAX_DURABLE_MESSAGE_CHARS as MAX_MESSAGE_CHARS,
    AckRequest,
    AcceptedRun,
    AdmitRunRequest,
    CancelRunRequest,
    RunResponseRequest,
    ThreadAddress,
)
from app.services.durable_runtime_integration_service import (
    DurableRuntimeIntegrationConflict,
    DurableRuntimeIntegrationInvalidResponse,
    DurableRuntimeIntegrationNotFound,
    DurableRuntimeIntegrationService,
    integration_event_key,
)
from app.services.durable_runtime_service import DurableRuntimeService

router = APIRouter(prefix="/integrations/durable-runs", tags=["durable-runtime-integrations"])
EVENT_POLL_SECONDS = 1.0
EVENT_HEARTBEAT_SECONDS = 15.0


def _event_key(user_id: UUID, integration_id: str, event_id: str, workspace_id: str = "") -> str:
    """Compatibility alias for integration event key generation."""
    return integration_event_key(user_id, integration_id, event_id, workspace_id)


def _event_cursor(after_sequence: int, last_event_id: str | None) -> int:
    if last_event_id is None:
        return after_sequence
    try:
        reconnect_cursor = int(last_event_id)
        if reconnect_cursor < 0:
            raise ValueError
    except ValueError as exc:
        raise HTTPException(400, "Last-Event-ID must be a nonnegative sequence") from exc
    return max(after_sequence, reconnect_cursor)


async def _owned_run(service: DurableRuntimeService, run_id: UUID, owner_id: UUID):
    run = await service.get_run(run_id)
    if run is None or run.owner_user_id != owner_id:
        raise HTTPException(404, "Run not found")
    return run


@router.post("", response_model=AcceptedRun, status_code=202)
async def admit_run(
    body: AdmitRunRequest,
    user: UserCtx = Depends(get_bearer_user),
    session: AsyncSession = Depends(db_uow),
) -> AcceptedRun:
    owner_id = UUID(str(user.id))
    if not get_settings().DURABLE_RUNTIME_ENABLED:
        raise HTTPException(503, "Durable runtime admission is disabled")
    tenants = await resolve_active_user_tenant_ids(session, user)
    if not tenants:
        raise HTTPException(403, "An active tenant membership is required")
    try:
        return await DurableRuntimeIntegrationService(session).admit(
            body, owner_user_id=owner_id, tenant_id=tenants[0],
        )
    except DurableRuntimeIntegrationConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{run_id}/responses")
async def respond_to_run(
    run_id: UUID,
    body: RunResponseRequest,
    user: UserCtx = Depends(get_bearer_user),
    session: AsyncSession = Depends(db_uow),
) -> dict[str, Any]:
    try:
        return await DurableRuntimeIntegrationService(session).respond(
            run_id,
            owner_user_id=UUID(str(user.id)),
            event_id=body.event_id,
            pause_id=body.pause_id,
            value=body.value,
        )
    except DurableRuntimeIntegrationNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except DurableRuntimeIntegrationInvalidResponse as exc:
        raise HTTPException(422, str(exc)) from exc
    except DurableRuntimeIntegrationConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{run_id}/cancel")
async def cancel_run(
    run_id: UUID,
    body: CancelRunRequest,
    user: UserCtx = Depends(get_bearer_user),
    session: AsyncSession = Depends(db_uow),
) -> dict[str, Any]:
    owner_id = UUID(str(user.id))
    service = DurableRuntimeService(session)
    run = await _owned_run(service, run_id, owner_id)
    try:
        run = await service.cancel(
            run_id,
            event_key=_event_key(owner_id, str((run.recipient or {}).get("integration_id", "")),
                                 body.event_id, str((run.recipient or {}).get("workspace_id", ""))),
            actor_user_id=owner_id,
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"run_id": str(run.id), "status": run.status}


def _event_payload(event: Any) -> dict[str, Any]:
    return {
        "event_id": str(event.id),
        "sequence": event.sequence,
        "kind": event.kind,
        "payload": event.payload,
        "created_at": event.created_at,
    }


@router.get("/{run_id}/events")
async def replay_events(
    run_id: UUID,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    user: UserCtx = Depends(get_bearer_user),
    session: AsyncSession = Depends(db_uow),
) -> dict[str, Any]:
    owner_id = UUID(str(user.id))
    service = DurableRuntimeService(session)
    await _owned_run(service, run_id, owner_id)
    events = await service.list_events(run_id, after_sequence=after_sequence,
                                       actor_user_id=owner_id, limit=limit)
    return {"items": [_event_payload(event) for event in events],
            "next_sequence": events[-1].sequence if events else after_sequence}


def _sse_event(event: Any) -> str:
    data = json.dumps(_event_payload(event), ensure_ascii=False,
                      default=lambda value: value.isoformat())
    return f"id: {event.sequence}\nevent: {event.kind}\ndata: {data}\n\n"


async def _stream_run_events(run_id: UUID, owner_id: UUID, after_sequence: int):
    cursor = after_sequence
    last_emit = asyncio.get_running_loop().time()
    yield "retry: 5000\n\n"
    while True:
        async with get_session_factory()() as session:
            service = DurableRuntimeService(session)
            run = await service.get_run(run_id)
            terminal = run is None or run.status in {"completed", "failed", "cancelled"}
            events = await service.list_events(
                run_id, after_sequence=cursor, actor_user_id=owner_id, limit=100,
            )
        if events:
            for event in events:
                yield _sse_event(event)
                cursor = event.sequence
            last_emit = asyncio.get_running_loop().time()
            if terminal and len(events) < 100:
                return
            continue
        if terminal:
            return
        now = asyncio.get_running_loop().time()
        if now - last_emit >= EVENT_HEARTBEAT_SECONDS:
            yield ": keep-alive\n\n"
            last_emit = now
        await asyncio.sleep(EVENT_POLL_SECONDS)


@router.get("/{run_id}/event-stream")
async def stream_events(
    run_id: UUID,
    after_sequence: int = Query(default=0, ge=0),
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    user: UserCtx = Depends(get_bearer_user),
    session: AsyncSession = Depends(db_session),
) -> StreamingResponse:
    owner_id = UUID(str(user.id))
    after_sequence = _event_cursor(after_sequence, last_event_id)
    await _owned_run(DurableRuntimeService(session), run_id, owner_id)
    await session.close()
    return StreamingResponse(
        _stream_run_events(run_id, owner_id, after_sequence),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{run_id}/events/{event_id}/ack", status_code=204,
             response_class=Response, response_model=None)
async def acknowledge_event(
    run_id: UUID,
    event_id: UUID,
    body: AckRequest | None = None,
    user: UserCtx = Depends(get_bearer_user),
    session: AsyncSession = Depends(db_uow),
) -> Response:
    owner_id = UUID(str(user.id))
    service = DurableRuntimeService(session)
    await _owned_run(service, run_id, owner_id)
    event = await service.get_event(run_id, event_id)
    if event is None:
        raise HTTPException(404, "Event not found")
    await service.ack_outgoing(event_id, external_message_id=body.external_message_id if body else None)
    return Response(status_code=204)
