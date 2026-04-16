"""Meta endpoints: available models, agents, direct LLM call."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user, get_llm_client
from app.core.http.clients import LLMClientProtocol
from app.core.security import UserCtx

router = APIRouter()


@router.get("/models")
async def list_llm_models():
    """Get list of available LLM models"""
    from app.core.config import get_settings
    settings = get_settings()

    models = []
    if settings.LLM_PROVIDER == "groq":
        models = [
            {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B", "provider": "groq"},
            {"id": "llama-3.1-70b-versatile", "name": "Llama 3.1 70B", "provider": "groq"},
            {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "provider": "groq"},
            {"id": "compound-beta", "name": "Compound Beta", "provider": "groq"},
        ]
    elif settings.LLM_PROVIDER == "openai":
        models = [
            {"id": "gpt-4-turbo-preview", "name": "GPT-4 Turbo", "provider": "openai"},
            {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "provider": "openai"},
        ]
    else:
        models = [
            {"id": "default", "name": "Default Model", "provider": settings.LLM_PROVIDER},
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
