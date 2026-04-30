"""Meta endpoints: available models, agents, direct LLM call."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user, get_llm_client
from app.core.http.clients import LLMClientProtocol
from app.core.security import UserCtx
from app.models.model_registry import Model, ModelType

router = APIRouter()


@router.get("/models")
async def list_llm_models(
    session: AsyncSession = Depends(db_session),
):
    """Get LLM models from registry (connector-driven, no env provider switch)."""
    result = await session.execute(
        select(Model)
        .where(
            Model.type == ModelType.LLM_CHAT,
            Model.enabled == True,  # noqa: E712
            Model.deleted_at.is_(None),
        )
        .order_by(Model.default_for_type.desc(), Model.updated_at.desc())
    )
    rows = result.scalars().all()
    models = [
        {
            "id": model.alias,
            "name": model.name,
            "provider": model.provider,
        }
        for model in rows
    ]
    return {"models": models}


@router.get("/agents")
async def list_chat_agents(
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
):
    """Get list of available agents for chat selection"""
    from app.services.agent_service import AgentService

    service = AgentService(session)
    agents, _ = await service.list_agents(limit=50)

    return {
        "agents": [
            {
                "slug": agent.slug,
                "name": agent.name,
                "description": agent.description,
            }
            for agent in agents
        ]
    }


@router.post("/chat")
async def chat(
    payload: Dict[str, Any],
    llm: LLMClientProtocol = Depends(get_llm_client),
) -> JSONResponse:
    messages: List[Dict[str, Any]] = payload.get("messages", [])
    params: Dict[str, Any] = payload.get("params", {})
    model: Optional[str] = payload.get("model")
    try:
        result = await llm.chat(messages, model=model, **params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return JSONResponse(result)
