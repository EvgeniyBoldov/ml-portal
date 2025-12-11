from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field


class PromptBase(BaseModel):
    slug: str = Field(..., description="Unique identifier", example="chat.rag.system")
    name: str = Field(..., description="Display name")
    description: Optional[str] = None
    template: str = Field(..., description="Jinja2 template")
    input_variables: Optional[List[str]] = []
    generation_config: Optional[Dict[str, Any]] = {}
    type: str = Field("chat", description="Prompt type: chat, agent, task")


class PromptCreate(PromptBase):
    pass


class PromptUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    template: Optional[str] = None
    input_variables: Optional[List[str]] = None
    generation_config: Optional[Dict[str, Any]] = None
    type: Optional[str] = None


class PromptResponse(PromptBase):
    id: UUID
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PromptRenderRequest(BaseModel):
    variables: Dict[str, Any]


class PromptRenderResponse(BaseModel):
    rendered: str
