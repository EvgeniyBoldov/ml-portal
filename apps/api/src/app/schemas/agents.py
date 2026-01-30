from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class AgentBindingInput(BaseModel):
    """Binding input for agent creation/update"""
    tool_id: UUID = Field(..., description="Tool ID")
    tool_instance_id: UUID = Field(..., description="Tool instance ID")
    credential_strategy: str = Field(default="any", description="Credential strategy: user_only, tenant_only, default_only, prefer_user, prefer_tenant, any")
    required: bool = Field(default=False, description="Is this tool required")


class AgentBase(BaseModel):
    slug: str = Field(..., description="Unique identifier", example="jira-assistant")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    system_prompt_slug: str = Field(..., description="Slug of the System Prompt")
    baseline_prompt_id: Optional[UUID] = Field(default=None, description="ID of the Baseline Prompt (restrictions)")
    policy_id: Optional[UUID] = Field(default=None, description="ID of the Policy (execution limits)")
    capabilities: List[str] = Field(default=[], description="Agent capabilities for Router matching")
    supports_partial_mode: bool = Field(default=False, description="Allow partial execution if some tools unavailable")
    generation_config: Optional[Dict[str, Any]] = {}
    is_active: bool = True
    enable_logging: bool = Field(default=True, description="Enable detailed run logging")


class AgentCreate(AgentBase):
    """Schema for creating an agent with bindings"""
    bindings: List[AgentBindingInput] = Field(default=[], description="Tool bindings")


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt_slug: Optional[str] = None
    baseline_prompt_id: Optional[UUID] = None
    policy_id: Optional[UUID] = None
    capabilities: Optional[List[str]] = None
    supports_partial_mode: Optional[bool] = None
    generation_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    enable_logging: Optional[bool] = None
    bindings: Optional[List[AgentBindingInput]] = Field(default=None, description="Replace all bindings")


class AgentBindingResponse(BaseModel):
    """Binding response with details"""
    id: UUID
    tool_id: UUID
    tool_slug: str
    tool_name: str
    tool_group_slug: str
    tool_instance_id: UUID
    instance_slug: str
    instance_name: str
    credential_strategy: str
    required: bool


class AgentResponse(AgentBase):
    id: UUID
    policy_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgentDetailResponse(AgentResponse):
    """Agent response with bindings"""
    bindings: List[AgentBindingResponse] = Field(default=[], description="Tool bindings with details")
