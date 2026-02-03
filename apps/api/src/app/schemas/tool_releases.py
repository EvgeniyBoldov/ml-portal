"""
Schemas for Tool Releases API
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# TOOL BACKEND RELEASE (read-only, from code)
# ─────────────────────────────────────────────────────────────────────────────

class ToolBackendReleaseResponse(BaseModel):
    """Backend release response (version from code)"""
    id: UUID
    tool_id: UUID
    version: str
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    description: Optional[str] = None
    method_name: str
    deprecated: bool = False
    deprecation_message: Optional[str] = None
    synced_at: datetime

    class Config:
        from_attributes = True


class ToolBackendReleaseListItem(BaseModel):
    """Backend release list item"""
    id: UUID
    version: str
    description: Optional[str] = None
    deprecated: bool = False
    synced_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# TOOL RELEASE (CRUD, for agents)
# ─────────────────────────────────────────────────────────────────────────────

class ToolReleaseCreate(BaseModel):
    """Create tool release request"""
    backend_release_id: UUID = Field(..., description="Backend release to use")
    config: Dict[str, Any] = Field(default_factory=dict, description="Additional configuration")
    description_for_llm: Optional[str] = Field(None, description="Description for LLM")
    category: Optional[str] = Field(None, description="Tool category")
    tags: List[str] = Field(default_factory=list, description="Tags for search")
    field_hints: Dict[str, str] = Field(default_factory=dict, description="Field hints")
    examples: List[Dict[str, Any]] = Field(default_factory=list, description="Usage examples")
    return_summary: Optional[str] = Field(None, description="Return value summary")
    notes: Optional[str] = Field(None, description="Release notes")


class ToolReleaseUpdate(BaseModel):
    """Update tool release request (only draft)"""
    backend_release_id: Optional[UUID] = Field(None, description="Backend release to use")
    config: Optional[Dict[str, Any]] = Field(None, description="Additional configuration")
    description_for_llm: Optional[str] = Field(None, description="Description for LLM")
    category: Optional[str] = Field(None, description="Tool category")
    tags: Optional[List[str]] = Field(None, description="Tags for search")
    field_hints: Optional[Dict[str, str]] = Field(None, description="Field hints")
    examples: Optional[List[Dict[str, Any]]] = Field(None, description="Usage examples")
    return_summary: Optional[str] = Field(None, description="Return value summary")
    notes: Optional[str] = Field(None, description="Release notes")


class ToolReleaseResponse(BaseModel):
    """Tool release response"""
    id: UUID
    tool_id: UUID
    version: int
    backend_release_id: UUID
    status: str
    config: Dict[str, Any]
    description_for_llm: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = []
    field_hints: Dict[str, str] = {}
    examples: List[Dict[str, Any]] = []
    return_summary: Optional[str] = None
    meta_hash: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    # Nested backend release info
    backend_release: Optional[ToolBackendReleaseListItem] = None

    class Config:
        from_attributes = True


class ToolReleaseListItem(BaseModel):
    """Tool release list item"""
    id: UUID
    version: int
    status: str
    backend_release_id: UUID
    backend_version: Optional[str] = None  # From backend_release.version
    category: Optional[str] = None
    tags: List[str] = []
    notes: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# TOOL (with releases)
# ─────────────────────────────────────────────────────────────────────────────

class ToolResponse(BaseModel):
    """Tool response"""
    id: UUID
    slug: str
    name: str
    name_for_llm: Optional[str] = None
    description: Optional[str] = None
    type: str
    tool_group_id: UUID
    is_active: bool
    recommended_release_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ToolDetailResponse(BaseModel):
    """Tool detail response with releases"""
    id: UUID
    slug: str
    name: str
    name_for_llm: Optional[str] = None
    description: Optional[str] = None
    type: str
    tool_group_id: UUID
    tool_group_slug: Optional[str] = None
    is_active: bool
    recommended_release_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    
    # Nested data
    backend_releases: List[ToolBackendReleaseListItem] = []
    releases: List[ToolReleaseListItem] = []
    recommended_release: Optional[ToolReleaseResponse] = None

    class Config:
        from_attributes = True


class ToolListItem(BaseModel):
    """Tool list item"""
    id: UUID
    slug: str
    name: str
    name_for_llm: Optional[str] = None
    description: Optional[str] = None
    type: str
    is_active: bool
    backend_releases_count: int = 0
    releases_count: int = 0
    has_recommended: bool = False

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# TOOL GROUP (with tools)
# ─────────────────────────────────────────────────────────────────────────────

class ToolGroupCreate(BaseModel):
    """Create tool group request"""
    slug: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class ToolGroupUpdate(BaseModel):
    """Update tool group request"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class ToolGroupResponse(BaseModel):
    """Tool group response"""
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ToolGroupDetailResponse(BaseModel):
    """Tool group detail response with tools"""
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime
    
    # Nested data
    tools: List[ToolListItem] = []
    instances_count: int = 0

    class Config:
        from_attributes = True


class ToolGroupListItem(BaseModel):
    """Tool group list item"""
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    tools_count: int = 0
    instances_count: int = 0

    class Config:
        from_attributes = True
