from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExecutionLimitsBase(BaseModel):
    llm_input_tokens_max: Optional[int] = Field(default=None, ge=1)
    llm_output_tokens_max: Optional[int] = Field(default=None, ge=1)
    llm_context_window_max: Optional[int] = Field(default=None, ge=1)
    runtime_steps_max: Optional[int] = Field(default=None, ge=1)
    runtime_tool_calls_max: Optional[int] = Field(default=None, ge=1)
    runtime_retries_max: Optional[int] = Field(default=None, ge=1)
    runtime_wall_time_ms_max: Optional[int] = Field(default=None, ge=1)
    runtime_tokens_total_max: Optional[int] = Field(default=None, ge=1)


class ExecutionLimitsUpdate(ExecutionLimitsBase):
    pass


class ExecutionLimitsResponse(ExecutionLimitsBase):
    id: Optional[UUID] = None
    scope_type: str
    scope_ref: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
