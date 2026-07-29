from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ExecutionLimitsBase(BaseModel):
    llm_input_tokens_max: Optional[int] = Field(default=None, ge=1)
    llm_output_tokens_max: Optional[int] = Field(default=None, ge=1)
    llm_context_window_max: Optional[int] = Field(default=None, ge=1)
    llm_timeout_s: Optional[int] = Field(default=None, ge=1)
    plan_revisions_max: Optional[int] = Field(default=None, ge=1)
    task_attempts_total_max: Optional[int] = Field(default=None, ge=1)
    agent_runs_total_max: Optional[int] = Field(default=None, ge=1)
    llm_calls_total_max: Optional[int] = Field(default=None, ge=1)
    tool_calls_total_max: Optional[int] = Field(default=None, ge=1)
    tokens_total_max: Optional[int] = Field(default=None, ge=1)
    execution_wall_time_ms_max: Optional[int] = Field(default=None, ge=1)
    run_ttl_ms: Optional[int] = Field(default=None, ge=1)
    planner_llm_calls_max: Optional[int] = Field(default=None, ge=1)
    planner_retries_max: Optional[int] = Field(default=None, ge=1)
    planner_tokens_total_max: Optional[int] = Field(default=None, ge=1)
    planner_execution_wall_time_ms_max: Optional[int] = Field(default=None, ge=1)
    agent_attempts_max: Optional[int] = Field(default=None, ge=1)
    agent_llm_calls_max: Optional[int] = Field(default=None, ge=1)
    agent_tool_calls_max: Optional[int] = Field(default=None, ge=1)
    agent_tokens_total_max: Optional[int] = Field(default=None, ge=1)
    agent_execution_wall_time_ms_max: Optional[int] = Field(default=None, ge=1)
    max_parallel_tasks: Optional[int] = Field(default=None, ge=1)


class ExecutionLimitsUpdate(ExecutionLimitsBase):
    pass


class ExecutionLimitsResponse(ExecutionLimitsBase):
    id: Optional[UUID] = None
    scope_type: str
    scope_ref: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
