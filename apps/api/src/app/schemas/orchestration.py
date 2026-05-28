"""
Orchestration schemas for API.

Only executor settings are exposed — router/planner models live in SystemLLMRole,
caps/gates live in PlatformSettings.
"""
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


class OrchestrationBase(BaseModel):
    """Base schema for Orchestration settings."""
    
    # === Executor Settings (used by AgentRuntime) ===
    executor_model: Optional[str] = Field(None, description="Default model alias for execution/generation")
    executor_temperature: Optional[float] = Field(0.7, description="Default temperature for execution/generation")
    tool_use_guard: Optional[str] = Field(None, description="Policy text for tool use (MANDATORY RULES)")


class ExecutorSettingsUpdate(BaseModel):
    """Schema for updating executor settings."""
    executor_model: Optional[str] = Field(None, description="Default model alias for execution/generation")
    executor_temperature: Optional[float] = Field(None, description="Default temperature for execution/generation")
    tool_use_guard: Optional[str] = Field(None, description="Policy text for tool use (MANDATORY RULES)")


class OrchestrationSettingsResponse(OrchestrationBase):
    """Schema for Orchestration settings response."""
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
