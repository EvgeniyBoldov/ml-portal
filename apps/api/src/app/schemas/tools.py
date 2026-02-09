"""
Tool schemas v2 - container with current_version_id, kind, tags.
"""
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class ToolCreate(BaseModel):
    slug: str = Field(..., description="Unique identifier, e.g. jira.search")
    tool_group_id: UUID
    name: str
    kind: str = Field("read", description="read | write | mixed")
    tags: Optional[List[str]] = None


class ToolUpdate(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    tags: Optional[List[str]] = None
    current_version_id: Optional[UUID] = None


class ToolResponse(BaseModel):
    id: UUID
    slug: str
    tool_group_id: UUID
    name: str
    current_version_id: Optional[UUID] = None
    kind: str
    tags: Optional[List[str]] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ToolDetailResponse(ToolResponse):
    tool_group_slug: Optional[str] = None
    tool_group_name: Optional[str] = None
