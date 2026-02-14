"""
Agent schemas v2 - versioned agent container.

Agent is a container (slug, name, description, current_version_id).
AgentVersion holds: prompt, policy_id, limit_id, version, status.
AgentBinding (tool_bind) belongs to agent_version_id.
"""
from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# AGENT CONTAINER
# ─────────────────────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    slug: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    logging_level: str = Field(default="brief", description="none, brief, full")


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    logging_level: Optional[str] = Field(default=None, description="none, brief, full")


class AgentResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    current_version_id: Optional[UUID] = None
    logging_level: str = Field(default="brief", description="none, brief, full")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# AGENT VERSION
# ─────────────────────────────────────────────────────────────────────────────

class AgentVersionCreate(BaseModel):
    prompt: Optional[str] = Field(default=None, description="System prompt text (inherited from parent if not provided)")
    policy_id: Optional[UUID] = Field(default=None, description="Policy ID")
    limit_id: Optional[UUID] = Field(default=None, description="Limit ID")
    notes: Optional[str] = None
    parent_version_id: Optional[UUID] = Field(default=None, description="Parent version ID for data inheritance")


class AgentVersionUpdate(BaseModel):
    prompt: Optional[str] = None
    policy_id: Optional[UUID] = None
    limit_id: Optional[UUID] = None
    notes: Optional[str] = None


class AgentVersionResponse(BaseModel):
    id: UUID
    agent_id: UUID
    version: int
    status: str
    prompt: str
    policy_id: Optional[UUID] = None
    limit_id: Optional[UUID] = None
    parent_version_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgentVersionInfo(BaseModel):
    """Short version info for list views"""
    id: UUID
    version: int
    status: str
    prompt: str
    policy_id: Optional[UUID] = None
    limit_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# AGENT DETAIL (container + versions)
# ─────────────────────────────────────────────────────────────────────────────

class AgentDetailResponse(AgentResponse):
    versions: List[AgentVersionInfo] = Field(default=[])
    current_version: Optional[AgentVersionInfo] = None


# ─────────────────────────────────────────────────────────────────────────────
# TOOL BINDINGS (per version)
# ─────────────────────────────────────────────────────────────────────────────

class AgentBindingInput(BaseModel):
    tool_id: UUID = Field(..., description="Tool ID")
    tool_instance_id: Optional[UUID] = Field(default=None, description="Tool instance ID (NULL = not bound)")
    credential_strategy: str = Field(
        default="ANY",
        description="USER_ONLY|TENANT_ONLY|PLATFORM_ONLY|USER_THEN_TENANT|TENANT_THEN_PLATFORM|ANY"
    )


class AgentBindingResponse(BaseModel):
    id: UUID
    agent_version_id: UUID
    tool_id: UUID
    tool_instance_id: Optional[UUID] = None
    credential_strategy: str
    created_at: datetime

    class Config:
        from_attributes = True
