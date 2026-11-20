from __future__ import annotations
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
import uuid

# Message role enum
MessageRole = Literal['system', 'user', 'assistant', 'tool']

class ChatMessage(BaseModel):
    """Chat message schema compatible with ORM"""
    model_config = {"from_attributes": True}
    
    id: Optional[uuid.UUID] = Field(None, description="Message ID")
    tenant_id: Optional[uuid.UUID] = Field(None, description="Tenant ID")
    chat_id: Optional[uuid.UUID] = Field(None, description="Chat ID")
    role: Literal['system', 'user', 'assistant', 'tool']
    content: Dict[str, Any] = Field(..., description="Message content as JSON dict")
    model: Optional[str] = Field(None, description="Model used for generation")
    tokens_in: Optional[int] = Field(None, description="Input tokens")
    tokens_out: Optional[int] = Field(None, description="Output tokens")
    version: Optional[int] = Field(1, description="Version for optimistic locking")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    meta: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v):
        """Validate content field - always dict format"""
        if isinstance(v, dict):
            # Ensure dict has required structure
            if not v:
                raise ValueError("Content cannot be empty dict")
            return v
        elif isinstance(v, str):
            # Convert string to dict format
            return {"text": v, "type": "text"}
        else:
            raise ValueError("Content must be string or dict")

class ChatMessageStreamRequest(BaseModel):
    model_config = {"extra": "forbid"}

    content: str = Field(..., min_length=1, max_length=32_000)
    artifact_ids: Optional[List[uuid.UUID]] = Field(default=None, max_length=10, description="Chat-scoped artifact IDs")

    @field_validator("content")
    @classmethod
    def validate_content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Content cannot be blank")
        return value


class ChatMemoryScopesUpdate(BaseModel):
    scope_keys: list[str] | None = Field(default=None, max_length=120)
    expected_revision: int = Field(ge=0)


class ChatContextInspectionResponse(BaseModel):
    revision: int
    focus: Dict[str, Any] = Field(default_factory=dict)
    active_goal: Optional[Dict[str, Any]] = None
    term_bindings: List[Dict[str, Any]] = Field(default_factory=list)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    open_loops: List[Dict[str, Any]] = Field(default_factory=list)
    decisions: List[Dict[str, Any]] = Field(default_factory=list)
    recent_anchor: Optional[Dict[str, Any]] = None
    task_results: List[Dict[str, Any]] = Field(default_factory=list)


class ChatContextResetResponse(BaseModel):
    revision: int
    closed_items: int


class ChatAttachmentUploadResponse(BaseModel):
    artifact_id: str
    file_name: str
    file_ext: str
    content_type: Optional[str] = None
    size_bytes: int
    status: str


class ChatUploadPolicyResponse(BaseModel):
    max_bytes: int
    allowed_extensions: List[str]
    allowed_content_types_by_extension: Dict[str, List[str]] = Field(default_factory=dict)


