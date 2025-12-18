from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class AgentBase(BaseModel):
    slug: str = Field(..., description="Unique identifier", example="netbox-helper")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    system_prompt_slug: str = Field(..., description="Slug of the System Prompt")
    tools: List[str] = Field(default=[], description="List of Tool slugs")
    generation_config: Optional[Dict[str, Any]] = {}
    is_active: bool = True
    enable_logging: bool = Field(default=True, description="Enable detailed run logging")


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt_slug: Optional[str] = None
    tools: Optional[List[str]] = None
    generation_config: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    enable_logging: Optional[bool] = None


class AgentResponse(AgentBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
