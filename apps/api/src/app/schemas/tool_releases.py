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
    schema_hash: Optional[str] = None
    worker_build_id: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    synced_at: datetime

    class Config:
        from_attributes = True


class ToolBackendReleaseListItem(BaseModel):
    """Backend release list item"""
    id: UUID
    version: str
    description: Optional[str] = None
    deprecated: bool = False
    schema_hash: Optional[str] = None
    worker_build_id: Optional[str] = None
    last_seen_at: Optional[datetime] = None
    synced_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# TOOL RELEASE (CRUD, for agents)
# ─────────────────────────────────────────────────────────────────────────────

class ToolReleaseCreate(BaseModel):
    """Create tool release request"""
    backend_release_id: UUID = Field(..., description="Backend release to use")
    from_release_id: Optional[UUID] = Field(None, description="Parent release to inherit meta-fields from")
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
    expected_schema_hash: Optional[str] = None
    parent_release_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    # Nested backend release info (full, with schemas)
    backend_release: Optional["ToolBackendReleaseResponse"] = None

    class Config:
        from_attributes = True


class ToolReleaseListItem(BaseModel):
    """Tool release list item"""
    id: UUID
    version: int
    status: str
    backend_release_id: UUID
    backend_version: Optional[str] = None  # From backend_release.version
    expected_schema_hash: Optional[str] = None
    parent_release_id: Optional[UUID] = None
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
    """Tool response (v2 container)"""
    id: UUID
    slug: str
    name: str
    kind: str
    tags: Optional[List[str]] = None
    tool_group_id: UUID
    current_version_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ToolDetailResponse(BaseModel):
    """Tool detail response with releases (v2)"""
    id: UUID
    slug: str
    name: str
    kind: str
    tags: Optional[List[str]] = None
    tool_group_id: UUID
    tool_group_slug: Optional[str] = None
    current_version_id: Optional[UUID] = None
    created_at: datetime

    backend_releases: List[ToolBackendReleaseListItem] = []
    releases: List[ToolReleaseListItem] = []
    current_version: Optional[ToolReleaseResponse] = None

    class Config:
        from_attributes = True


class ToolListItem(BaseModel):
    """Tool list item (v2)"""
    id: UUID
    slug: str
    name: str
    kind: str
    tags: Optional[List[str]] = None
    backend_releases_count: int = 0
    releases_count: int = 0
    has_current_version: bool = False

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# TOOL GROUP (with tools)
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA DIFF
# ─────────────────────────────────────────────────────────────────────────────

class SchemaDiffField(BaseModel):
    """A field in a schema diff"""
    name: str
    type: str = "unknown"
    required: bool = False
    description: str = ""


class SchemaDiffChangedField(BaseModel):
    """A field whose type changed"""
    name: str
    old_type: str
    new_type: str


class SchemaDiffResponse(BaseModel):
    """Schema diff between two backend releases"""
    added_fields: List[SchemaDiffField] = []
    removed_fields: List[SchemaDiffField] = []
    changed_fields: List[SchemaDiffChangedField] = []


class ToolGroupCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    type: Optional[str] = None
    description_for_router: Optional[str] = None


class ToolGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    type: Optional[str] = None
    description_for_router: Optional[str] = None


class ToolGroupResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    description_for_router: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ToolGroupDetailResponse(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    description_for_router: Optional[str] = None
    created_at: datetime

    tools: List[ToolListItem] = []
    instances_count: int = 0

    class Config:
        from_attributes = True


class ToolGroupListItem(BaseModel):
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    type: Optional[str] = None
    tools_count: int = 0
    instances_count: int = 0

    class Config:
        from_attributes = True
