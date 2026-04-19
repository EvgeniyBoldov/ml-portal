from typing import Any, Dict, List, Optional, Literal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict


# Status and Type literals
PromptStatusType = Literal["draft", "active", "archived"]
PromptTypeType = Literal["prompt", "baseline"]


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT CONTAINER schemas
# ─────────────────────────────────────────────────────────────────────────────

class PromptContainerCreate(BaseModel):
    """Create new prompt container"""
    slug: str = Field(..., description="Unique identifier", example="chat.rag.system")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    type: PromptTypeType = Field("prompt", description="Prompt type: prompt or baseline")


class PromptContainerUpdate(BaseModel):
    """Update prompt container metadata"""
    name: Optional[str] = None
    description: Optional[str] = None


class PromptContainerResponse(BaseModel):
    """Prompt container response"""
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    type: PromptTypeType
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT VERSION schemas
# ─────────────────────────────────────────────────────────────────────────────

class PromptVersionCreate(BaseModel):
    """Create new version of a prompt"""
    template: str = Field(..., description="Jinja2 template")
    parent_version_id: Optional[UUID] = Field(None, description="ID of the version to create from")
    input_variables: Optional[List[str]] = None
    generation_config: Optional[Dict[str, Any]] = Field(default_factory=dict)


class PromptVersionUpdate(BaseModel):
    """Update draft version (only drafts can be edited)"""
    template: Optional[str] = None
    input_variables: Optional[List[str]] = None
    generation_config: Optional[Dict[str, Any]] = None


class PromptVersionActivate(BaseModel):
    """Activate a draft version"""
    archive_current: bool = Field(True, description="Archive currently active version")


class PromptVersionResponse(BaseModel):
    """Full version response"""
    id: UUID
    prompt_id: UUID
    template: str
    input_variables: List[str] = Field(default_factory=list)
    generation_config: Dict[str, Any] = Field(default_factory=dict)
    version: int
    status: PromptStatusType
    parent_version_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class PromptVersionInfo(BaseModel):
    """Short version info for list"""
    id: UUID
    version: int
    status: PromptStatusType
    template: Optional[str] = None
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# COMBINED schemas (for convenience)
# ─────────────────────────────────────────────────────────────────────────────

class PromptListItem(BaseModel):
    """Prompt item for list view"""
    id: UUID  # Container ID
    slug: str
    name: str
    description: Optional[str] = None
    type: PromptTypeType
    versions_count: int
    latest_version: Optional[int] = None
    active_version: Optional[int] = None
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class PromptDetailResponse(BaseModel):
    """Detailed prompt response with container + versions"""
    # Container info
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    type: PromptTypeType
    created_at: datetime
    updated_at: datetime
    
    # Recommended version
    recommended_version_id: Optional[UUID] = None
    recommended_version: Optional[PromptVersionInfo] = None
    
    # Versions
    versions: List[PromptVersionInfo]


# ─────────────────────────────────────────────────────────────────────────────
# RENDER & VALIDATE schemas
# ─────────────────────────────────────────────────────────────────────────────

class PromptRenderRequest(BaseModel):
    """Request to render a prompt template"""
    variables: Dict[str, Any]


class PromptRenderResponse(BaseModel):
    """Rendered prompt result"""
    rendered: str


class PromptValidateRequest(BaseModel):
    """Request to validate prompt template"""
    template: str


class PromptValidateResponse(BaseModel):
    """Validation result"""
    valid: bool
    variables: List[str] = Field(default_factory=list, description="Variables found in template")
    error: Optional[str] = None
