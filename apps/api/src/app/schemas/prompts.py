from typing import Any, Dict, List, Optional, Literal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


# Status and Type literals
PromptStatusType = Literal["draft", "active", "archived"]
PromptTypeType = Literal["prompt", "baseline"]


class PromptBase(BaseModel):
    """Base prompt fields"""
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    template: str = Field(..., description="Jinja2 template")
    input_variables: Optional[List[str]] = Field(default_factory=list)
    generation_config: Optional[Dict[str, Any]] = Field(default_factory=dict)


class PromptCreate(PromptBase):
    """Create new prompt (first version)"""
    slug: str = Field(..., description="Unique identifier", example="chat.rag.system")
    type: PromptTypeType = Field("prompt", description="Prompt type: prompt or baseline")


class PromptVersionCreate(PromptBase):
    """Create new version from existing prompt"""
    parent_version_id: UUID = Field(..., description="ID of the version to create from")


class PromptUpdate(BaseModel):
    """Update draft prompt (only drafts can be edited)"""
    name: Optional[str] = None
    description: Optional[str] = None
    template: Optional[str] = None
    input_variables: Optional[List[str]] = None
    generation_config: Optional[Dict[str, Any]] = None


class PromptActivate(BaseModel):
    """Activate a draft prompt"""
    archive_current: bool = Field(True, description="Archive currently active version")


class PromptVersionInfo(BaseModel):
    """Short version info for list"""
    id: UUID
    version: int
    status: PromptStatusType
    created_at: datetime
    
    class Config:
        from_attributes = True


class AgentUsingPrompt(BaseModel):
    """Agent info for prompt usage"""
    slug: str
    name: str
    version: int  # Which version of prompt this agent uses


class PromptResponse(BaseModel):
    """Full prompt response"""
    id: UUID
    slug: str
    name: str
    description: Optional[str] = None
    template: str
    input_variables: List[str] = Field(default_factory=list)
    generation_config: Dict[str, Any] = Field(default_factory=dict)
    type: PromptTypeType
    version: int
    status: PromptStatusType
    parent_version_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PromptListItem(BaseModel):
    """Prompt item for list view (shows latest version info)"""
    slug: str
    name: str
    description: Optional[str] = None
    type: PromptTypeType
    latest_version: int
    active_version: Optional[int] = None
    versions_count: int
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PromptDetailResponse(BaseModel):
    """Detailed prompt response with versions and usage"""
    slug: str
    name: str
    description: Optional[str] = None
    type: PromptTypeType
    versions: List[PromptVersionInfo]
    used_by_agents: List[AgentUsingPrompt] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class PromptRenderRequest(BaseModel):
    variables: Dict[str, Any]


class PromptRenderResponse(BaseModel):
    rendered: str


class PromptValidateRequest(BaseModel):
    """Request to validate prompt variables against agent context"""
    template: str
    agent_slug: Optional[str] = None


class PromptValidateResponse(BaseModel):
    """Validation result"""
    valid: bool
    template_variables: List[str] = Field(default_factory=list, description="Variables found in template")
    available_variables: List[str] = Field(default_factory=list, description="Variables available from agent context")
    missing_variables: List[str] = Field(default_factory=list, description="Variables in template but not available")
    unused_variables: List[str] = Field(default_factory=list, description="Available variables not used in template")
