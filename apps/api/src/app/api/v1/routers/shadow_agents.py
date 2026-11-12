"""Authenticated JSON-only entry point for shadow agents."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_bearer_user, get_llm_client, resolve_active_user_tenant_ids
from app.core.http.clients import LLMClientProtocol
from app.core.middleware import get_request_id
from app.core.security import UserCtx
from app.schemas.shadow_agents import ShadowAgentAccepted, ShadowAgentTask, ShadowAgentRequest, ShadowAgentResponse
from app.services.shadow_invocation_service import ShadowInvocationService
from app.services.shadow_agent_service import ShadowAgentService

router = APIRouter(tags=["shadow-agents"])


@router.post("/agents/shadow/invoke", response_model=ShadowAgentResponse | ShadowAgentAccepted,
             responses={202: {"model": ShadowAgentAccepted, "description": "Async invocation accepted"}})
async def invoke_shadow_agent(
    payload: ShadowAgentRequest, request: Request, response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: UserCtx = Depends(get_bearer_user),
    session: AsyncSession = Depends(db_session),
    llm: LLMClientProtocol = Depends(get_llm_client),
) -> ShadowAgentResponse | ShadowAgentAccepted:
    if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 255):
        raise HTTPException(422, "Idempotency-Key must be nonblank and at most 255 characters")
    tenant_ids = await resolve_active_user_tenant_ids(session, user)
    if not tenant_ids:
        raise HTTPException(403, "An active tenant membership is required")
    agent_service = ShadowAgentService(session, llm)
    if payload.async_:
        invocation_id = await ShadowInvocationService(session, agent_service).enqueue(
            payload, user_id=UUID(str(user.id)), tenant_id=tenant_ids[0], scopes=user.scopes or [],
            request_id=str(get_request_id(request) or str(uuid4())),
            idempotency_key=idempotency_key,
        )
        response.status_code = 202
        return ShadowAgentAccepted(id=invocation_id)
    return await agent_service.invoke(
        payload, user_id=UUID(str(user.id)), tenant_id=tenant_ids[0],
        scopes=user.scopes or [], request_id=str(get_request_id(request) or str(uuid4())),
    )


@router.get("/agents/shadow/results", response_model=list[ShadowAgentTask])
async def list_shadow_results(
    user: UserCtx = Depends(get_bearer_user),
    session: AsyncSession = Depends(db_session),
    llm: LLMClientProtocol = Depends(get_llm_client),
) -> list[ShadowAgentTask]:
    tenant_ids = await resolve_active_user_tenant_ids(session, user)
    if not tenant_ids:
        raise HTTPException(403, "An active tenant membership is required")
    return await ShadowInvocationService(session, ShadowAgentService(session, llm)).list_ready(
        UUID(str(user.id)), tenant_ids=[UUID(str(value)) for value in tenant_ids])


@router.get("/agents/shadow/results/{invocation_id}", response_model=ShadowAgentTask)
async def get_shadow_result(
    invocation_id: UUID,
    user: UserCtx = Depends(get_bearer_user),
    session: AsyncSession = Depends(db_session),
    llm: LLMClientProtocol = Depends(get_llm_client),
) -> ShadowAgentTask:
    tenant_ids = await resolve_active_user_tenant_ids(session, user)
    if not tenant_ids:
        raise HTTPException(403, "An active tenant membership is required")
    return await ShadowInvocationService(session, ShadowAgentService(session, llm)).get(
        invocation_id, UUID(str(user.id)), tenant_ids=[UUID(str(value)) for value in tenant_ids])


@router.post("/agents/shadow/results/{invocation_id}/ack", status_code=204)
async def acknowledge_shadow_result(
    invocation_id: UUID,
    user: UserCtx = Depends(get_bearer_user),
    session: AsyncSession = Depends(db_session),
    llm: LLMClientProtocol = Depends(get_llm_client),
) -> None:
    tenant_ids = await resolve_active_user_tenant_ids(session, user)
    if not tenant_ids:
        raise HTTPException(403, "An active tenant membership is required")
    await ShadowInvocationService(session, ShadowAgentService(session, llm)).acknowledge(
        invocation_id, UUID(str(user.id)), tenant_ids=[UUID(str(value)) for value in tenant_ids])
