"""
AI Generation router - generate content for agent/tool versions using LLM
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.logging import get_logger

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.agent_service import AgentService
from app.models.agent import Agent
from app.models.agent_version import AgentVersion
from app.services.llm_service import LLMService

router = APIRouter(prefix="/ai-generate", tags=["ai-generate"])

logger = get_logger(__name__)


class VersionGenerateRequest(BaseModel):
    description: str = Field(..., description="Описание агента или инструмента")
    fields: List[str] = Field(..., description="Список полей для заполнения")
    context: Optional[Dict[str, Any]] = Field(None, description="Дополнительный контекст")


class VersionGenerateResponse(BaseModel):
    filled_fields: Dict[str, Any] = Field(..., description="Заполненные поля")
    suggestions: List[str] = Field(..., description="Предложения по улучшению")


@router.post("/agents/{agent_id}/versions/generate")
async def generate_agent_version(
    agent_id: UUID,
    data: VersionGenerateRequest,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Сгенерировать контент для версии агента с помощью ИИ"""
    try:
        agent_service = AgentService(db)
        agent = await agent_service.get_agent(agent_id)
        
        # Получить существующие версии для контекста
        versions_result = await db.execute(
            select(AgentVersion)
            .where(AgentVersion.agent_id == agent_id)
            .order_by(AgentVersion.version.desc())
            .limit(3)
        )
        existing_versions = versions_result.scalars().all()
        
        # Собрать контекст
        context = {
            "agent_name": agent.name,
            "agent_description": agent.description,
            "existing_versions": [
                {
                    "version": v.version,
                    "identity": v.identity,
                    "mission": v.mission,
                    "scope": v.scope,
                }
                for v in existing_versions
            ],
        }
        
        if data.context:
            context.update(data.context)
        
        # Описания полей для агента
        field_descriptions = {
            "identity": "Кем является агент, его роль и личность",
            "mission": "Основная задача и цель агента",
            "scope": "Границы возможностей и ограничения",
            "rules": "Правила поведения и этические ограничения",
            "tool_use_rules": "Правила использования инструментов",
            "output_format": "Формат вывода результатов",
            "examples": "Примеры использования (в виде JSON массива)",
            "short_info": "Краткое описание для роутинга",
            "tags": "Теги для категоризации (в виде JSON массива)",
            "routing_keywords": "Ключевые слова для роутинга (в виде JSON массива)",
            "routing_negative_keywords": "Стоп-слова для роутинга (в виде JSON массива)",
        }
        
        # Вызвать LLM
        llm_service = LLMService()
        filled_fields = await llm_service.generate_version_content(
            entity_type="agent",
            description=data.description,
            fields=data.fields,
            field_descriptions=field_descriptions,
            context=context
        )
        
        # Генерировать предложения
        suggestions = await llm_service.generate_suggestions(
            entity_type="agent",
            description=data.description,
            filled_fields=filled_fields,
            context=context
        )
        
        return VersionGenerateResponse(
            filled_fields=filled_fields,
            suggestions=suggestions
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate agent version: {str(e)}"
        )


@router.post("/tools/{tool_id}/versions/generate", deprecated=True, include_in_schema=False)
async def _removed_generate_tool_version(tool_id: UUID) -> None:
    """Removed: tool semantic/policy layer was dropped. Stub kept to return 410 until clients update."""
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="AI generation for tool releases is removed; MCP schema is the source of truth.",
    )


