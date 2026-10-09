"""
Pydantic schemas for Limit API.
"""
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


LimitStatusType = Literal["draft", "active", "deprecated"]


# ─────────────────────────────────────────────────────────────────────────────
# LIMIT CONTAINER schemas
# ─────────────────────────────────────────────────────────────────────────────

class LimitContainerCreate(BaseModel):
    slug: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None


class LimitContainerUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class LimitContainerResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    current_version_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# LIMIT VERSION schemas
# ─────────────────────────────────────────────────────────────────────────────

class LimitVersionCreate(BaseModel):
    max_steps: Optional[int] = Field(None, description="Max agent steps")
    max_tool_calls: Optional[int] = Field(None, description="Max tool calls")
    max_wall_time_ms: Optional[int] = Field(None, description="Max wall time in ms")
    tool_timeout_ms: Optional[int] = Field(None, description="Tool timeout in ms")
    max_retries: Optional[int] = Field(None, description="Max retries")
    extra_config: Optional[Dict[str, Any]] = Field(None, description="Extra config")
    notes: Optional[str] = Field(None, description="Notes about this version")
    parent_version_id: Optional[UUID] = Field(None, description="Parent version ID")


class LimitVersionUpdate(BaseModel):
    max_steps: Optional[int] = None
    max_tool_calls: Optional[int] = None
    max_wall_time_ms: Optional[int] = None
    tool_timeout_ms: Optional[int] = None
    max_retries: Optional[int] = None
    extra_config: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None


class LimitVersionResponse(BaseModel):
    id: UUID
    limit_id: UUID
    version: int
    status: LimitStatusType
    max_steps: Optional[int] = None
    max_tool_calls: Optional[int] = None
    max_wall_time_ms: Optional[int] = None
    tool_timeout_ms: Optional[int] = None
    max_retries: Optional[int] = None
    extra_config: Dict[str, Any] = {}
    parent_version_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LimitVersionInfo(BaseModel):
    id: UUID
    version: int
    status: LimitStatusType
    max_steps: Optional[int] = None
    max_tool_calls: Optional[int] = None
    max_wall_time_ms: Optional[int] = None
    tool_timeout_ms: Optional[int] = None
    max_retries: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# COMBINED schemas
# ─────────────────────────────────────────────────────────────────────────────

class LimitListItem(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    current_version_id: Optional[UUID] = None
    versions_count: int
    latest_version: Optional[int] = None
    active_version: Optional[int] = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LimitDetailResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    current_version_id: Optional[UUID] = None
    current_version: Optional[LimitVersionInfo] = None
    versions: List[LimitVersionInfo]
