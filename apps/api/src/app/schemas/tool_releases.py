"""
Schemas for Tool Releases API
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL RELEASE (CRUD, for agents)
# ─────────────────────────────────────────────────────────────────────────────

class ToolReleaseCreate(BaseModel):
    """Create tool release request"""
    backend_release_id: Optional[UUID] = Field(None, description="Backend release to use (optional for draft)")
    from_release_id: Optional[UUID] = Field(None, description="Parent release to inherit meta-fields from")


class ToolReleaseUpdate(BaseModel):
    """Update tool release request (only draft)"""
    backend_release_id: Optional[UUID] = Field(None, description="Backend release to use")


class ToolReleaseResponse(BaseModel):
    """Tool release response"""
    id: UUID
    tool_id: UUID
    version: int
    backend_release_id: Optional[UUID] = None
    status: str
    # Meta
    meta_hash: Optional[str] = None
    expected_schema_hash: Optional[str] = None
    parent_release_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    # Nested backend release info (full, with schemas)
    backend_release: Optional["ToolBackendReleaseResponse"] = None

    model_config = ConfigDict(from_attributes=True)


class ToolReleaseListItem(BaseModel):
    """Tool release list item"""
    id: UUID
    version: int
    status: str
    backend_release_id: Optional[UUID] = None
    backend_version: Optional[str] = None
    expected_schema_hash: Optional[str] = None
    parent_release_id: Optional[UUID] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
