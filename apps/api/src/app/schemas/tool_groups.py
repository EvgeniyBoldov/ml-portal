"""
Pydantic schemas for ToolGroup API
"""
from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field


class ToolGroupCreate(BaseModel):
    """Schema for creating a tool group"""
    slug: str = Field(..., description="Unique slug (e.g., 'jira', 'rag', 'netbox')")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None


class ToolGroupUpdate(BaseModel):
    """Schema for updating a tool group"""
    name: Optional[str] = None
    description: Optional[str] = None


class ToolGroupResponse(BaseModel):
    """Schema for tool group response"""
    id: UUID
    slug: str
    name: str
    description: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
