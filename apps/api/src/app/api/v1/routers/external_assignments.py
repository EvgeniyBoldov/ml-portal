"""Trusted connector interface for assignments and return delivery."""
from secrets import compare_digest
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow
from app.api.v1.routers.durable_runtime import _event_payload
from app.core.config import get_settings
from app.repositories.api_tokens_repo import ApiTokensRepository
from app.schemas.durable_runtime import AcceptedRun, AckRequest
from app.schemas.external_assignment import AssignmentAnswer, AssignmentCancel, AssignmentRequest, Connector, ExternalUser
from app.services.assignment_integrations import AssignmentIntegrationsService
from app.services.durable_runtime_integration_service import (
    DurableRuntimeIntegrationConflict,
    DurableRuntimeIntegrationInvalidResponse,
    DurableRuntimeIntegrationNotFound,
    DurableRuntimeIntegrationService,
    integration_event_key,
)
from app.services.durable_runtime_service import DurableRuntimeConflict, DurableRuntimeService
from app.services.external_assignment_identity_service import AssignmentIdentityNotLinked, ExternalAssignmentIdentityService

router = APIRouter(prefix="/integrations/assignments", tags=["external-assignments"])


Session = Annotated[AsyncSession, Depends(db_uow)]


async def authenticate_connector(
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
    x_assignment_connector: Annotated[str | None, Header()] = None,
) -> Connector:
    key = x_assignment_connector or ""
    scheme, _, token = (authorization or "").partition(" ")
    error = HTTPException(401, "Invalid connector credentials", headers={"WWW-Authenticate": "Bearer"})
    if scheme.lower() != "bearer" or not token:
        raise error
    try:
        kind, connector_id = key.split(":", 1)
        connector = Connector(type=kind, id=connector_id)
    except ValueError as exc:
        raise error from exc

    service = AssignmentIntegrationsService(session)
    integration = await service.repo.by_source(key)
    if integration is not None:
        if not await service.authenticate(integration, token):
            raise error
    else:
        expected = get_settings().ASSIGNMENT_CONNECTOR_TOKENS.get(key)
        if expected is None or not compare_digest(token.encode(), expected.get_secret_value().encode()):
            raise error
    return connector


Principal = Annotated[Connector, Depends(authenticate_connector)]


async def _user(session: AsyncSession, connector: Connector, identity: ExternalUser, *, allow_link: bool = False):
    try:
        return await ExternalAssignmentIdentityService(session).resolve(connector, identity, allow_link=allow_link)
    except AssignmentIdentityNotLinked as exc:
        raise HTTPException(403, detail={"code": "identity_not_linked"}) from exc


async def _run(service: DurableRuntimeService, run_id: UUID, principal: Connector, *, binding: str):
    run = await service.get_run(run_id)
    envelope = ((run.recipient or {}).get("assignment") or {}) if run is not None else {}
    if not envelope or envelope.get(binding) != principal.model_dump():
        raise HTTPException(404, "Run not found")
    return run, envelope


@router.post("", status_code=202, response_model=AcceptedRun)
async def admit(body: AssignmentRequest, session: Session, principal: Principal) -> AcceptedRun:
    settings = get_settings()
    if not settings.DURABLE_RUNTIME_ENABLED:
        raise HTTPException(503, "Durable runtime admission is disabled")
    if principal != body.source:
        raise HTTPException(403, detail={"code": "source_not_allowed"})
    allowed = settings.ASSIGNMENT_REPLY_ROUTES.get(principal.key, [principal.key])
    if body.reply_to.key not in allowed:
        raise HTTPException(403, detail={"code": "reply_channel_not_allowed"})
    if body.reply_to.key != principal.key:
        target = await AssignmentIntegrationsService(session).repo.by_source(body.reply_to.key)
        if not (target.is_active if target is not None else body.reply_to.key in settings.ASSIGNMENT_CONNECTOR_TOKENS):
            raise HTTPException(403, detail={"code": "reply_channel_not_allowed"})
    try:
        admission = body.to_admission()
    except ValidationError as exc:
        raise HTTPException(422, "Invalid assignment data or destination") from exc

    user = await _user(session, principal, body.user, allow_link=True)
    tenant_ids = await ApiTokensRepository(session).active_tenant_ids(user.id)
    if not tenant_ids:
        raise HTTPException(403, detail={"code": "tenant_required"})
    reply_to = body.reply_to.model_dump(mode="json")
    envelope = {
        "source": principal.model_dump(),
        "reply_connector": body.reply_to.model_dump(include={"type", "id"}),
        "reply_to": reply_to,
        "user": {"clouds": str(body.user.clouds)},
    }
    try:
        return await DurableRuntimeIntegrationService(session).admit(
            admission, owner_user_id=user.id, tenant_id=UUID(tenant_ids[0]), connector_context=envelope,
        )
    except DurableRuntimeIntegrationConflict as exc:
        raise HTTPException(409, str(exc)) from exc


async def _actor(session: AsyncSession, principal: Connector, run_id: UUID, identity: ExternalUser):
    service = DurableRuntimeService(session)
    run, envelope = await _run(service, run_id, principal, binding="source")
    if str(identity.clouds) != envelope["user"]["clouds"]:
        raise HTTPException(404, "Run not found")
    user = await _user(session, principal, identity)
    memberships = await ApiTokensRepository(session).active_tenant_ids(user.id)
    if user.id != run.owner_user_id:
        raise HTTPException(404, "Run not found")
    if run.request_payload["tenant_id"] not in memberships:
        raise HTTPException(403, detail={"code": "tenant_required"})
    return service, run


@router.post("/{run_id}/responses")
async def respond(run_id: UUID, body: AssignmentAnswer, session: Session, principal: Principal):
    _, run = await _actor(session, principal, run_id, body.user)
    try:
        return await DurableRuntimeIntegrationService(session).respond(
            run_id, owner_user_id=run.owner_user_id, event_id=body.event_id, pause_id=body.pause_id, value=body.value,
        )
    except DurableRuntimeIntegrationInvalidResponse as exc:
        raise HTTPException(422, str(exc)) from exc
    except DurableRuntimeIntegrationConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except DurableRuntimeIntegrationNotFound as exc:
        raise HTTPException(404, "Run not found") from exc


@router.post("/{run_id}/cancel")
async def cancel(run_id: UUID, body: AssignmentCancel, session: Session, principal: Principal):
    service, run = await _actor(session, principal, run_id, body.user)
    try:
        outcome = await service.cancel(
            run_id, event_key=integration_event_key(run.owner_user_id, principal.key, body.event_id, principal.id),
            actor_user_id=run.owner_user_id,
        )
    except DurableRuntimeConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"run_id": str(run_id), "status": outcome.status}


@router.get("/deliveries")
async def deliveries(session: Session, principal: Principal, limit: int = Query(default=100, ge=1, le=500)):
    ids = await DurableRuntimeService(session).pending_assignment_deliveries(principal.type, principal.id, limit)
    return {"run_ids": ids}


@router.get("/{run_id}/events")
async def events(run_id: UUID, session: Session, principal: Principal,
                 after_sequence: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500)):
    service = DurableRuntimeService(session)
    run, envelope = await _run(service, run_id, principal, binding="reply_connector")
    rows = await service.list_events(run_id, after_sequence=after_sequence, actor_user_id=run.owner_user_id, limit=limit)
    return {"items": [_event_payload(row) for row in rows],
            "next_sequence": rows[-1].sequence if rows else after_sequence,
            "run_id": str(run_id), "user": envelope["user"], "reply_to": envelope["reply_to"]}


@router.post("/{run_id}/events/{event_id}/ack", status_code=204)
async def acknowledge(run_id: UUID, event_id: UUID, body: AckRequest, session: Session, principal: Principal) -> Response:
    service = DurableRuntimeService(session)
    await _run(service, run_id, principal, binding="reply_connector")
    if await service.get_event(run_id, event_id) is None:
        raise HTTPException(404, "Event not found")
    await service.ack_outgoing(event_id, external_message_id=body.external_message_id)
    return Response(status_code=204)
