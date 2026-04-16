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
from app.services.tool_release_service import ToolReleaseService
from app.models.agent import Agent
from app.models.agent_version import AgentVersion
from app.models.tool import Tool
from app.models.tool_release import ToolRelease
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


@router.post("/tools/{tool_id}/versions/generate")
async def generate_tool_version(
    tool_id: UUID,
    data: VersionGenerateRequest,
    db: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(require_admin),
):
    """Сгенерировать контент для версии инструмента с помощью ИИ"""
    try:
        tool_service = ToolReleaseService(db)
        tool = await tool_service.get_tool_by_id(tool_id)
        
        # Получить существующие версии для контекста
        versions_result = await db.execute(
            select(ToolRelease)
            .where(ToolRelease.tool_id == tool_id)
            .order_by(ToolRelease.version.desc())
            .limit(3)
        )
        existing_versions = versions_result.scalars().all()
        
        # Собрать контекст
        context = {
            "tool_name": tool.name,
            "tool_description": tool.name,
            "existing_versions": [
                {
                    "version": v.version,
                    "semantic_profile": v.semantic_profile,
                    "policy_hints": v.policy_hints,
                }
                for v in existing_versions
            ],
        }
        
        if data.context:
            context.update(data.context)
        
        # Описания полей для инструмента
        field_descriptions = {
            "semantic_profile": "Структурированный профайл инструмента",
            "semantic_profile.summary": "Краткое описание инструмента для LLM",
            "semantic_profile.when_to_use": "Когда использовать инструмент",
            "semantic_profile.limitations": "Ограничения и неудачные сценарии",
            "semantic_profile.examples": "Примеры использования (по одному на строку)",
            "policy_hints": "Структурированные подсказки политики",
            "policy_hints.dos": "Разрешённые и предпочтительные сценарии",
            "policy_hints.donts": "Запрещённые сценарии",
            "policy_hints.guardrails": "Стоп-факторы и границы",
            "policy_hints.sensitive_inputs": "Чувствительные входы",
        }
        
        # Вызвать LLM
        logger.info(f"Starting tool version generation: tool_id={tool_id}, fields={data.fields}")
        llm_service = LLMService()
        filled_fields = await llm_service.generate_version_content(
            entity_type="tool",
            description=data.description,
            fields=data.fields,
            field_descriptions=field_descriptions,
            context=context
        )
        logger.info(f"LLM generation completed successfully: {len(filled_fields)} fields")
        
        # Генерировать предложения
        suggestions = await llm_service.generate_suggestions(
            entity_type="tool",
            description=data.description,
            filled_fields=filled_fields,
            context=context
        )
        
        return VersionGenerateResponse(
            filled_fields=filled_fields,
            suggestions=suggestions
        )
        
    except Exception as e:
        import traceback
        logger.error(f"Error in generate_tool_version: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate tool version: {str(e)}"
        )
