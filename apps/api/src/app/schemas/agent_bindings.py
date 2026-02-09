"""
Pydantic schemas for AgentBinding API v2.

Bindings belong to AgentVersion, not Agent directly.
"""
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum


class CredentialStrategyEnum(str, Enum):
    """Credential strategy options (v2)"""
    USER_ONLY = "USER_ONLY"
    TENANT_ONLY = "TENANT_ONLY"
    PLATFORM_ONLY = "PLATFORM_ONLY"
    USER_THEN_TENANT = "USER_THEN_TENANT"
    TENANT_THEN_PLATFORM = "TENANT_THEN_PLATFORM"
    ANY = "ANY"


class AgentBindingCreate(BaseModel):
    """Schema for creating an agent binding (per version)"""
    agent_version_id: UUID = Field(..., description="Agent version ID")
    tool_id: UUID = Field(..., description="Tool ID")
    tool_instance_id: Optional[UUID] = Field(default=None, description="Tool instance ID (NULL = not bound)")
    credential_strategy: CredentialStrategyEnum = Field(
        default=CredentialStrategyEnum.ANY,
        description="Credential resolution strategy"
    )


class AgentBindingUpdate(BaseModel):
    """Schema for updating an agent binding"""
    tool_instance_id: Optional[UUID] = None
    credential_strategy: Optional[CredentialStrategyEnum] = None


class AgentBindingResponse(BaseModel):
    """Schema for agent binding response"""
    id: UUID
    agent_version_id: UUID
    tool_id: UUID
    tool_instance_id: Optional[UUID] = None
    credential_strategy: str
    created_at: datetime

    class Config:
        from_attributes = True


class AgentBindingDetailResponse(AgentBindingResponse):
    """Schema for agent binding with related entity details"""
    tool_slug: Optional[str] = None
    tool_name: Optional[str] = None
    tool_group_slug: Optional[str] = None
    instance_slug: Optional[str] = None
    instance_name: Optional[str] = None
