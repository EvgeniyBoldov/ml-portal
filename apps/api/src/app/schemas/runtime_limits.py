"""Typed HTTP contracts for runtime guards and actor execution limits."""
from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RuntimeLimitsUpdate(BaseModel):
    wall_time_ms_max: Optional[int] = Field(default=None, ge=1)
    max_parallel_tasks: Optional[int] = Field(default=None, ge=1)
    max_replans: Optional[int] = Field(default=None, ge=0)
    max_task_executions: Optional[int] = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")


class RuntimeLimitsResponse(RuntimeLimitsUpdate):
    sources: Optional[Dict[str, str]] = None


class ActorLimitsUpdate(BaseModel):
    llm_calls_max: Optional[int] = Field(default=None, ge=1)
    tool_calls_max: Optional[int] = Field(default=None, ge=1)
    wall_time_ms_max: Optional[int] = Field(default=None, ge=1)

    model_config = ConfigDict(extra="forbid")


class ActorLimitsResponse(BaseModel):
    own: ActorLimitsUpdate
    effective: ActorLimitsUpdate
    sources: Dict[str, str]


class OrchestratorLimitsUpdate(ActorLimitsUpdate):
    @model_validator(mode="after")
    def reject_tools(self) -> "OrchestratorLimitsUpdate":
        if self.tool_calls_max is not None:
            raise ValueError("tool_calls_max is only valid for agents")
        return self
