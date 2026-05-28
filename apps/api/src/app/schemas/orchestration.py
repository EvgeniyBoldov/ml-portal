"""
Orchestration schemas for API.

Only executor settings are exposed — router/planner models live in SystemLLMRole,
caps/gates live in PlatformSettings.
"""
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class OrchestrationBase(BaseModel):
    """Базовая схема настроек оркестрации."""
    
    # === Executor Settings (used by AgentRuntime) ===
    executor_model: Optional[str] = Field(None, description="Псевдоним модели по умолчанию для выполнения/генерации")
    executor_temperature: Optional[float] = Field(0.7, description="Температура по умолчанию для выполнения/генерации")
    tool_use_guard: Optional[str] = Field(None, description="Текст политики использования инструментов (ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА)")
    retry_instruction: Optional[str] = Field(None, description="Инструкция для повтора при отсутствии вызова операции")
    intent_messages: Optional[Dict[str, str]] = Field(None, description="Сообщения намерений (i18n)")
    prompt_budgets: Optional[Dict[str, Any]] = Field(None, description="Бюджеты промптов (magic numbers)")
    prompt_labels: Optional[Dict[str, str]] = Field(None, description="Лейблы промптов (i18n)")


class ExecutorSettingsUpdate(BaseModel):
    """Схема для обновления настроек исполнителя."""
    executor_model: Optional[str] = Field(None, description="Псевдоним модели по умолчанию для выполнения/генерации")
    executor_temperature: Optional[float] = Field(None, description="Температура по умолчанию для выполнения/генерации")
    tool_use_guard: Optional[str] = Field(None, description="Текст политики использования инструментов (ОБЯЗАТЕЛЬНЫЕ ПРАВИЛА)")
    retry_instruction: Optional[str] = Field(None, description="Инструкция для повтора при отсутствии вызова операции")
    intent_messages: Optional[Dict[str, str]] = Field(None, description="Сообщения намерений (i18n)")
    prompt_budgets: Optional[Dict[str, Any]] = Field(None, description="Бюджеты промптов (magic numbers)")
    prompt_labels: Optional[Dict[str, str]] = Field(None, description="Лейблы промптов (i18n)")


class OrchestrationSettingsResponse(OrchestrationBase):
    """Схема ответа настроек оркестрации."""
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
