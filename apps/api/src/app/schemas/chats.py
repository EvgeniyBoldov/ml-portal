from __future__ import annotations
from typing import Optional, List, Dict, Any, Literal, Union
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date
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

class ChatTurnRequest(BaseModel):
    response_stream: Optional[bool] = Field(None)
    use_rag: Optional[bool] = Field(None)
    rag_params: Optional[Dict[str, Any]] = Field(None)
    messages: Optional[List[ChatMessage]] = Field(None)
    temperature: Optional[float] = Field(None)
    max_tokens: Optional[int] = Field(None)
    idempotency_key: Optional[str] = Field(None)

class ChatTurnResponse(BaseModel):
    chat_id: Optional[str] = Field(None)
    message_id: Optional[str] = Field(None)
    created_at: Optional[datetime] = Field(None)
    assistant_message: Optional[ChatMessage] = Field(None)
    usage: Optional[Dict[str, Any]] = Field(None)
    rag: Optional[Dict[str, Any]] = Field(None)


class ChatCreateRequest(BaseModel):
    """Request schema for creating a chat"""
    model_config = {"from_attributes": True}
    
    name: Optional[str] = Field(None, description="Chat name", max_length=255)
    tags: Optional[List[str]] = Field(None, description="Chat tags")


class ChatResponse(BaseModel):
    """Response schema for chat operations"""
    model_config = {"from_attributes": True}
    
    id: uuid.UUID = Field(..., description="Chat ID")
    tenant_id: uuid.UUID = Field(..., description="Tenant ID")
    name: Optional[str] = Field(None, description="Chat name")
    owner_id: uuid.UUID = Field(..., description="Owner ID")
    tags: Optional[List[str]] = Field(None, description="Chat tags")
    version: int = Field(..., description="Version for optimistic locking")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_message_at: Optional[datetime] = Field(None, description="Last message timestamp")


class ChatListResponse(BaseModel):
    """Response schema for chat list"""
    chats: List[ChatResponse] = Field(..., description="List of chats")
    total: int = Field(..., description="Total number of chats")
    page: int = Field(..., description="Current page")
    size: int = Field(..., description="Page size")


class ChatMessageCreateRequest(BaseModel):
    """Request schema for creating a chat message"""
    model_config = {"from_attributes": True}
    
    role: Literal['system', 'user', 'assistant', 'tool']
    content: Dict[str, Any] = Field(..., description="Message content as JSON dict")
    model: Optional[str] = Field(None, description="Model used for generation")
    meta: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v):
        """Validate content field for message creation - always dict format"""
        if isinstance(v, dict):
            # Ensure dict has required structure
            if not v:
                raise ValueError("Content cannot be empty dict")
            return v
        elif isinstance(v, str):
            # Convert string to dict format
            if not v.strip():
                raise ValueError("Content cannot be empty")
            return {"text": v, "type": "text"}
        else:
            raise ValueError("Content must be string or dict")


class ChatMessageResponse(BaseModel):
    """Response schema for chat message operations"""
    model_config = {"from_attributes": True}
    
    id: uuid.UUID = Field(..., description="Message ID")
    tenant_id: uuid.UUID = Field(..., description="Tenant ID")
    chat_id: uuid.UUID = Field(..., description="Chat ID")
    role: str = Field(..., description="Message role")
    content: Dict[str, Any] = Field(..., description="Message content as JSON dict")
    model: Optional[str] = Field(None, description="Model used for generation")
    tokens_in: Optional[int] = Field(None, description="Input tokens")
    tokens_out: Optional[int] = Field(None, description="Output tokens")
    version: int = Field(..., description="Version for optimistic locking")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    meta: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class ChatMessageListResponse(BaseModel):
    """Response schema for chat message list"""
    messages: List[ChatMessageResponse] = Field(..., description="List of messages")
    total: int = Field(..., description="Total number of messages")
    page: int = Field(..., description="Current page")
    size: int = Field(..., description="Page size")


class ChatUpdateRequest(BaseModel):
    """Request schema for updating a chat"""
    model_config = {"from_attributes": True}
    
    name: Optional[str] = Field(None, description="Chat name", max_length=255)
    tags: Optional[List[str]] = Field(None, description="Chat tags - None to keep unchanged, [] to clear")
    
    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v):
        """Validate tags field"""
        if v is not None and len(v) > 10:
            raise ValueError("Maximum 10 tags allowed")
        return v
