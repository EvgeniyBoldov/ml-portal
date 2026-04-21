"""Schemas for Plan API responses and requests."""

from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime

from pydantic import BaseModel, Field, ConfigDict

from app.models.plan import PlanStatus


class PlannerStepResponse(BaseModel):
    """Response schema for a planner step."""
    step_id: str
    kind: str = Field(..., pattern="^(agent|tool|llm|ask_user)$")
    title: str
    description: Optional[str] = None
    dependencies: List[str] = Field(default_factory=list)
    risk_level: str = Field(..., pattern="^(low|medium|high|destructive)$")
    on_fail: str = Field(..., pattern="^(retry|replan|ask_user|abort)$")
    requires_confirmation: bool
    input: Dict[str, Any] = Field(default_factory=dict)
    ref: Optional[str] = None
    op: Optional[str] = None


class PlannerPlanResponse(BaseModel):
    """Response schema for a planner plan."""
    goal: str
    steps: List[PlannerStepResponse]


class PlanResponse(BaseModel):
    """Response schema for a plan."""
    id: UUID
    chat_id: UUID
    agent_run_id: Optional[UUID]
    plan_data: PlannerPlanResponse
    status: PlanStatus
    current_step: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class PlanStatusUpdate(BaseModel):
    """Schema for updating plan status."""
    status: PlanStatus
    current_step: Optional[int] = None


class PlanCreate(BaseModel):
    """Schema for creating a plan (internal use)."""
    chat_id: UUID
    agent_run_id: Optional[UUID]
    plan_data: PlannerPlanResponse


class PlanSummary(BaseModel):
    """Summary schema for plan lists."""
    id: UUID
    chat_id: UUID
    status: PlanStatus
    steps_count: int
    current_step: int
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
