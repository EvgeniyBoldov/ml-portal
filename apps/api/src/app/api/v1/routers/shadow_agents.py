"""Authenticated JSON-only entry point for shadow agents."""
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user, get_llm_client, resolve_active_user_tenant_ids
from app.core.http.clients import LLMClientProtocol
from app.core.middleware import get_request_id
from app.core.security import UserCtx
from app.schemas.shadow_agents import ShadowAgentRequest, ShadowAgentResponse
from app.services.shadow_agent_service import ShadowAgentService

router = APIRouter(tags=["shadow-agents"])


def shadow_user(request: Request) -> UserCtx:
    if not request.headers.get("Authorization", "").startswith("Bearer "):
        raise HTTPException(401, "Bearer access token required", headers={"WWW-Authenticate": "Bearer"})
    return get_current_user(request)


@router.post("/agents/shadow/invoke", response_model=ShadowAgentResponse)
async def invoke_shadow_agent(
    payload: ShadowAgentRequest, request: Request,
    user: UserCtx = Depends(shadow_user),
    session: AsyncSession = Depends(db_session),
    llm: LLMClientProtocol = Depends(get_llm_client),
) -> ShadowAgentResponse:
    tenant_ids = await resolve_active_user_tenant_ids(session, user)
    if not tenant_ids:
        raise HTTPException(403, "An active tenant membership is required")
    return await ShadowAgentService(session, llm).invoke(
        payload, user_id=UUID(str(user.id)), tenant_id=tenant_ids[0],
        scopes=user.scopes or [], request_id=str(get_request_id(request) or str(uuid4())),
    )
