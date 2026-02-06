"""
Pydantic schemas for Baseline API.
Baseline is a separate entity from Prompt for managing restrictions and rules.
"""
from typing import List, Optional, Literal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# Status and Scope literals
BaselineStatusType = Literal["draft", "active", "archived"]
BaselineScopeType = Literal["default", "tenant", "user"]


# ─────────────────────────────────────────────────────────────────────────────
# BASELINE CONTAINER schemas
# ─────────────────────────────────────────────────────────────────────────────

class BaselineContainerCreate(BaseModel):
    """Create new baseline container"""
    slug: str = Field(..., description="Unique identifier", example="security.no-code")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    scope: BaselineScopeType = Field("default", description="Scope: default, tenant, or user")
    tenant_id: Optional[UUID] = Field(None, description="Required for tenant scope")
    user_id: Optional[UUID] = Field(None, description="Required for user scope")
    is_active: bool = Field(True, description="Whether baseline is active")


class BaselineContainerUpdate(BaseModel):
    """Update baseline container metadata"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class BaselineContainerResponse(BaseModel):
    """Baseline container response"""
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    scope: BaselineScopeType
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# BASELINE VERSION schemas
# ─────────────────────────────────────────────────────────────────────────────

class BaselineVersionCreate(BaseModel):
    """Create new version of a baseline"""
    template: str = Field(..., description="Baseline content (restrictions/rules)")
    parent_version_id: Optional[UUID] = Field(None, description="ID of the version to create from")
    notes: Optional[str] = Field(None, description="Notes about this version")


class BaselineVersionUpdate(BaseModel):
    """Update draft version (only drafts can be edited)"""
    template: Optional[str] = None
    notes: Optional[str] = None


class BaselineVersionActivate(BaseModel):
    """Activate a draft version"""
    archive_current: bool = Field(True, description="Archive currently active version")


class BaselineVersionResponse(BaseModel):
    """Full version response"""
    id: UUID
    baseline_id: UUID
    template: str
    version: int
    status: BaselineStatusType
    parent_version_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class BaselineVersionInfo(BaseModel):
    """Short version info for list"""
    id: UUID
    version: int
    status: BaselineStatusType
    notes: Optional[str] = None
    template: Optional[str] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────────────────────
# COMBINED schemas (for convenience)
# ─────────────────────────────────────────────────────────────────────────────

class BaselineListItem(BaseModel):
    """Baseline item for list view"""
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    scope: BaselineScopeType
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    is_active: bool
    versions_count: int
    latest_version: Optional[int] = None
    active_version: Optional[int] = None
    updated_at: datetime
    
    class Config:
        from_attributes = True


class BaselineDetailResponse(BaseModel):
    """Detailed baseline response with container + versions"""
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    scope: BaselineScopeType
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    # Recommended version
    recommended_version_id: Optional[UUID] = None
    recommended_version: Optional[BaselineVersionInfo] = None
    
    versions: List[BaselineVersionInfo]


# ─────────────────────────────────────────────────────────────────────────────
# EFFECTIVE BASELINES schemas
# ─────────────────────────────────────────────────────────────────────────────

class EffectiveBaselinesRequest(BaseModel):
    """Request to get effective baselines for a user/tenant"""
    tenant_id: Optional[UUID] = None
    user_id: Optional[UUID] = None


class EffectiveBaselineItem(BaseModel):
    """Effective baseline item"""
    id: UUID
    slug: str
    name: str
    scope: BaselineScopeType
    template: str  # Active version template


class EffectiveBaselinesResponse(BaseModel):
    """Effective baselines response"""
    baselines: List[EffectiveBaselineItem]
    merged_content: str = Field(..., description="All baselines merged into one string")
