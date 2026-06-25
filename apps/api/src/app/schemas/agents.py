"""
Agent schemas v2 - versioned agent container.

Pattern:
- AgentListItem       — short schema for lists (no nested objects)
- AgentDetailResponse  — detail schema with nested version list
"""
from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


# ─────────────────────────────────────────────────────────────────────────────
# AGENT CONTAINER
# ─────────────────────────────────────────────────────────────────────────────

class AgentCreate(BaseModel):
    slug: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    tags: Optional[List[str]] = Field(default=None, description="Agent tags for catalog filtering")
    logging_level: str = Field(default="brief", description="none | errors | brief | full")
    model: Optional[str] = Field(default=None, description="LLM model alias")
    temperature: Optional[float] = Field(default=None, description="LLM temperature (orchestration default if None)")
    requires_confirmation_for_write: Optional[bool] = Field(default=None, description="Require confirmation for write ops")
    risk_level: Optional[str] = Field(default=None, description="low, medium, high")
    allow_all_collections: bool = Field(default=False, description="If true, agent may access all current and future collections allowed by RBAC.")
    allowed_collection_ids: Optional[List[UUID]] = Field(default=None, description="Whitelist of Collection IDs bound to agent. Empty/NULL with allow_all_collections=false means no collection access.")
    provides_keys: Optional[List[str]] = Field(default=None, description="Machine keys this agent can resolve for planner needs-routing (e.g. ['lun_uuid']).")


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    logging_level: Optional[str] = Field(default=None, description="none, brief, full")
    model: Optional[str] = Field(default=None, description="LLM model alias")
    temperature: Optional[float] = None
    requires_confirmation_for_write: Optional[bool] = None
    risk_level: Optional[str] = None
    allow_all_collections: Optional[bool] = None
    allowed_collection_ids: Optional[List[UUID]] = None
    provides_keys: Optional[List[str]] = None


class AgentResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    current_version_id: Optional[UUID] = None
    logging_level: str = Field(default="brief", description="none | errors | brief | full")
    model: Optional[str] = None
    temperature: Optional[float] = None
    requires_confirmation_for_write: Optional[bool] = None
    risk_level: Optional[str] = None
    allow_all_collections: bool = False
    allowed_collection_ids: Optional[List[UUID]] = None
    provides_keys: Optional[List[str]] = None
    lifecycle_status: str = "active"
    deprecated_at: Optional[datetime] = None
    retention_days: int = 14
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentListItem(BaseModel):
    """Short schema for GET /agents list."""
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    current_version_id: Optional[UUID] = None
    logging_level: str = "brief"
    model: Optional[str] = None
    temperature: Optional[float] = None
    requires_confirmation_for_write: Optional[bool] = None
    risk_level: Optional[str] = None
    allow_all_collections: bool = False
    allowed_collection_ids: Optional[List[UUID]] = None
    provides_keys: Optional[List[str]] = None
    lifecycle_status: str = "active"
    deprecated_at: Optional[datetime] = None
    retention_days: int = 14
    versions_count: int = 0
    current_version_number: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# AGENT VERSION
# ─────────────────────────────────────────────────────────────────────────────

class AgentVersionCreate(BaseModel):
    # Prompt parts
    identity: Optional[str] = Field(default=None, description="Role/persona")
    mission: Optional[str] = Field(default=None, description="What the agent does")
    scope: Optional[str] = Field(default=None, description="Boundaries: what it does / does NOT do")
    rules: Optional[str] = Field(default=None, description="Guidelines/algorithm")
    tool_use_rules: Optional[str] = Field(default=None, description="How/when to call tools")
    output_format: Optional[str] = Field(default=None, description="Response structure/JSON schema")
    examples: Optional[str] = Field(default=None, description="Few-shot examples")
    planner_short_info: Optional[str] = Field(default=None, description="Короткое описание для планера")
    # Safety prompt constraints
    never_do: Optional[str] = Field(default=None, description="Explicit prohibitions")
    allowed_ops: Optional[str] = Field(default=None, description="Allowed operations")
    tags: Optional[List[str]] = Field(default=None, description="Version-specific tags")
    # Meta
    notes: Optional[str] = None
    parent_version_id: Optional[UUID] = Field(default=None, description="Parent version ID for data inheritance")


class AgentVersionUpdate(BaseModel):
    # Prompt parts
    identity: Optional[str] = None
    mission: Optional[str] = None
    scope: Optional[str] = None
    rules: Optional[str] = None
    tool_use_rules: Optional[str] = None
    output_format: Optional[str] = None
    examples: Optional[str] = None
    planner_short_info: Optional[str] = None
    # Safety prompt constraints
    never_do: Optional[str] = None
    allowed_ops: Optional[str] = None
    tags: Optional[List[str]] = None
    # Meta
    notes: Optional[str] = None


class AgentVersionResponse(BaseModel):
    id: UUID
    agent_id: UUID
    version: int
    status: str
    # Prompt parts
    identity: Optional[str] = None
    mission: Optional[str] = None
    scope: Optional[str] = None
    rules: Optional[str] = None
    tool_use_rules: Optional[str] = None
    output_format: Optional[str] = None
    examples: Optional[str] = None
    planner_short_info: Optional[str] = None
    # Safety prompt constraints
    never_do: Optional[str] = None
    allowed_ops: Optional[str] = None
    tags: Optional[List[str]] = None
    # Meta
    parent_version_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentVersionInfo(BaseModel):
    """Short version info for list views"""
    id: UUID
    version: int
    status: str
    identity: Optional[str] = None
    mission: Optional[str] = None
    planner_short_info: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# ─────────────────────────────────────────────────────────────────────────────
# AGENT DETAIL (container + versions)
# ─────────────────────────────────────────────────────────────────────────────

class AgentDetailResponse(AgentResponse):
    versions: List[AgentVersionResponse] = Field(default=[])
