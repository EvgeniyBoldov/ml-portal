"""
Agent schemas v2 - versioned agent container.

Pattern:
- AgentListItem       — short schema for lists (no nested objects)
- AgentDetailResponse  — detail schema with nested version list
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
    tags: Optional[List[str]] = Field(default=None, description="Agent tags for catalog filtering")
    logging_level: str = Field(default="brief", description="none, brief, full")
    model: Optional[str] = Field(default=None, description="LLM model override")
    allowed_collection_ids: Optional[List[UUID]] = Field(default=None, description="Whitelist of Collection IDs bound to agent. NULL = all collections.")


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    logging_level: Optional[str] = Field(default=None, description="none, brief, full")
    model: Optional[str] = Field(default=None, description="LLM model override")
    allowed_collection_ids: Optional[List[UUID]] = None


class AgentResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    current_version_id: Optional[UUID] = None
    logging_level: str = Field(default="brief", description="none, brief, full")
    model: Optional[str] = None
    allowed_collection_ids: Optional[List[UUID]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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
    allowed_collection_ids: Optional[List[UUID]] = None
    versions_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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
    # Execution config
    model: Optional[str] = Field(default=None, description="LLM model override")
    timeout_s: Optional[int] = Field(default=None, description="Timeout in seconds")
    max_steps: Optional[int] = Field(default=None, description="Max tool-call loop steps")
    max_retries: Optional[int] = Field(default=None, description="Max retries on failure")
    max_tokens: Optional[int] = Field(default=None, description="Max output tokens")
    temperature: Optional[float] = Field(default=None, description="LLM temperature")
    # Safety knobs
    requires_confirmation_for_write: Optional[bool] = Field(default=None, description="Require confirmation for write ops")
    risk_level: Optional[str] = Field(default=None, description="low, medium, high")
    never_do: Optional[str] = Field(default=None, description="Explicit prohibitions")
    allowed_ops: Optional[str] = Field(default=None, description="Allowed operations")
    # Routing
    short_info: Optional[str] = Field(default=None, description="Short description for routing")
    tags: Optional[List[str]] = Field(default=None, description="Version-specific tags for routing")
    is_routable: bool = Field(default=False, description="Whether this version can be selected by router")
    routing_keywords: Optional[List[str]] = Field(default=None, description="Keywords for routing (5-30)")
    routing_negative_keywords: Optional[List[str]] = Field(default=None, description="Negative keywords for routing")
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
    # Execution config
    model: Optional[str] = None
    timeout_s: Optional[int] = None
    max_steps: Optional[int] = None
    max_retries: Optional[int] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    # Safety knobs
    requires_confirmation_for_write: Optional[bool] = None
    risk_level: Optional[str] = None
    never_do: Optional[str] = None
    allowed_ops: Optional[str] = None
    # Routing
    short_info: Optional[str] = None
    tags: Optional[List[str]] = None
    is_routable: Optional[bool] = None
    routing_keywords: Optional[List[str]] = None
    routing_negative_keywords: Optional[List[str]] = None
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
    # Execution config
    model: Optional[str] = None
    timeout_s: Optional[int] = None
    max_steps: Optional[int] = None
    max_retries: Optional[int] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    # Safety knobs
    requires_confirmation_for_write: Optional[bool] = None
    risk_level: Optional[str] = None
    never_do: Optional[str] = None
    allowed_ops: Optional[str] = None
    # Routing
    short_info: Optional[str] = None
    tags: Optional[List[str]] = None
    is_routable: bool = False
    routing_keywords: Optional[List[str]] = None
    routing_negative_keywords: Optional[List[str]] = None
    # Meta
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
    identity: Optional[str] = None
    mission: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# ─────────────────────────────────────────────────────────────────────────────
# AGENT DETAIL (container + versions)
# ─────────────────────────────────────────────────────────────────────────────

class AgentDetailResponse(AgentResponse):
    versions: List[AgentVersionResponse] = Field(default=[])
