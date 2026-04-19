"""
Tool schemas v2 - publication container + current_version_id.

Pattern:
- ToolListItem      — short schema for lists (counts only, no nested objects)
- ToolDetailResponse — detail schema with nested releases and backend releases
"""
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.tool_releases import (
    ToolReleaseListItem,
    ToolReleaseResponse,
    ToolBackendReleaseListItem,
)


# ─── Mutations ────────────────────────────────────────────────────────

class ToolCreate(BaseModel):
    slug: str = Field(..., description="Unique identifier, e.g. jira.search")
    name: str
    domains: List[str] = Field(default_factory=list, description="Runtime domains/tags")
    tags: Optional[List[str]] = None


class ToolUpdate(BaseModel):
    name: Optional[str] = None
    domains: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    current_version_id: Optional[UUID] = None


# ─── List / Detail ────────────────────────────────────────────────────

class ToolListItem(BaseModel):
    """Short schema for tool lists."""
    id: UUID
    slug: str
    name: str
    domains: List[str] = Field(default_factory=list)
    tags: Optional[List[str]] = None
    current_version_id: Optional[UUID] = None
    backend_releases_count: int = 0
    releases_count: int = 0
    has_current_version: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ToolDetailResponse(BaseModel):
    """Detail schema for GET /tools/{id} — full tool with nested releases."""
    id: UUID
    slug: str
    name: str
    domains: List[str] = Field(default_factory=list)
    tags: Optional[List[str]] = None
    current_version_id: Optional[UUID] = None
    created_at: datetime

    backend_releases: List[ToolBackendReleaseListItem] = []
    releases: List[ToolReleaseListItem] = []
    current_version: Optional[ToolReleaseResponse] = None

    model_config = ConfigDict(from_attributes=True)
