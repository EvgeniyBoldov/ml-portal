"""
Pydantic schemas for AgentBinding API
"""
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class CredentialStrategyEnum(str, Enum):
    """Credential strategy options"""
    USER_ONLY = "user_only"
    TENANT_ONLY = "tenant_only"
    DEFAULT_ONLY = "default_only"
    PREFER_USER = "prefer_user"
    PREFER_TENANT = "prefer_tenant"
    ANY = "any"


class AgentBindingCreate(BaseModel):
    """Schema for creating an agent binding"""
    agent_id: UUID = Field(..., description="Agent ID")
    tool_id: UUID = Field(..., description="Tool ID (specific operation like jira.create)")
    tool_instance_id: UUID = Field(..., description="Tool instance ID (e.g., jira-prod)")
    credential_strategy: CredentialStrategyEnum = Field(
        default=CredentialStrategyEnum.ANY,
        description="Credential resolution strategy"
    )
    required: bool = Field(default=False, description="Is this tool required for agent to work")


class AgentBindingUpdate(BaseModel):
    """Schema for updating an agent binding"""
    tool_instance_id: Optional[UUID] = None
    credential_strategy: Optional[CredentialStrategyEnum] = None
    required: Optional[bool] = None


class AgentBindingResponse(BaseModel):
    """Schema for agent binding response"""
    id: UUID
    agent_id: UUID
    tool_id: UUID
    tool_instance_id: UUID
    credential_strategy: str
    required: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgentBindingDetailResponse(AgentBindingResponse):
    """Schema for agent binding with related entity details"""
    tool_slug: Optional[str] = None
    tool_name: Optional[str] = None
    tool_group_slug: Optional[str] = None
    instance_slug: Optional[str] = None
    instance_name: Optional[str] = None
