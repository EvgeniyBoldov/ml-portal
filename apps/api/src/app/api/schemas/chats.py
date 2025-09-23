"""
Chat-related API schemas
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from enum import Enum

class MessageRole(str, Enum):
    """Message roles"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

# Request schemas
class ChatCreateRequest(BaseModel):
    """Chat creation request"""
    name: Optional[str] = Field(None, max_length=200, description="Chat name")
    tags: Optional[List[str]] = Field(default_factory=list, description="Chat tags")
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if v is not None and not v.strip():
            return None
        return v.strip() if v else None
    
    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v):
        if v is None:
            return []
        if len(v) > 10:
            raise ValueError('Too many tags (max 10)')
        for tag in v:
            if not isinstance(tag, str):
                raise ValueError('All tags must be strings')
            if len(tag) > 50:
                raise ValueError('Tag too long (max 50 characters)')
            if not tag.strip():
                raise ValueError('Empty tags not allowed')
        return [tag.strip() for tag in v if tag.strip()]

class ChatUpdateRequest(BaseModel):
    """Chat update request"""
    name: Optional[str] = Field(None, max_length=200, description="New chat name")
    tags: Optional[List[str]] = Field(None, description="New chat tags")
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if v is not None and not v.strip():
            return None
        return v.strip() if v else None
    
    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v):
        if v is None:
            return None
        if len(v) > 10:
            raise ValueError('Too many tags (max 10)')
        for tag in v:
            if not isinstance(tag, str):
                raise ValueError('All tags must be strings')
            if len(tag) > 50:
                raise ValueError('Tag too long (max 50 characters)')
            if not tag.strip():
                raise ValueError('Empty tags not allowed')
        return [tag.strip() for tag in v if tag.strip()]

class ChatTagsUpdateRequest(BaseModel):
    """Chat tags update request"""
    tags: List[str] = Field(..., description="New chat tags")
    
    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v):
        if len(v) > 10:
            raise ValueError('Too many tags (max 10)')
        for tag in v:
            if not isinstance(tag, str):
                raise ValueError('All tags must be strings')
            if len(tag) > 50:
                raise ValueError('Tag too long (max 50 characters)')
            if not tag.strip():
                raise ValueError('Empty tags not allowed')
        return [tag.strip() for tag in v if tag.strip()]

class ChatSearchRequest(BaseModel):
    """Chat search request"""
    query: Optional[str] = Field(None, min_length=2, max_length=100, description="Search query")
    tag: Optional[str] = Field(None, min_length=1, max_length=50, description="Filter by tag")
    limit: int = Field(50, ge=1, le=100, description="Number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")

class ChatMessageCreateRequest(BaseModel):
    """Chat message creation request"""
    role: MessageRole = Field(..., description="Message role")
    content: Dict[str, Any] = Field(..., description="Message content")
    model: Optional[str] = Field(None, max_length=100, description="Model used")
    tokens_in: Optional[int] = Field(None, ge=0, description="Input tokens")
    tokens_out: Optional[int] = Field(None, ge=0, description="Output tokens")
    meta: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v):
        if not v or not isinstance(v, dict):
            raise ValueError('Content must be a non-empty dictionary')
        return v

class ChatMessageSearchRequest(BaseModel):
    """Chat message search request"""
    query: str = Field(..., min_length=2, max_length=100, description="Search query")
    role: Optional[MessageRole] = Field(None, description="Filter by role")
    limit: int = Field(50, ge=1, le=100, description="Number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")

class ChatMessagesListRequest(BaseModel):
    """Chat messages list request"""
    limit: int = Field(50, ge=1, le=100, description="Number of results")
    cursor: Optional[str] = Field(None, description="Cursor for pagination")
    role: Optional[MessageRole] = Field(None, description="Filter by role")

# Response schemas
class ChatResponse(BaseModel):
    """Chat response"""
    id: str = Field(..., description="Chat ID")
    name: Optional[str] = Field(None, description="Chat name")
    tags: List[str] = Field(default_factory=list, description="Chat tags")
    owner_id: str = Field(..., description="Owner user ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    last_message_at: Optional[datetime] = Field(None, description="Last message timestamp")
    
    class Config:
        from_attributes = True

class ChatListResponse(BaseModel):
    """Chat list response"""
    chats: List[ChatResponse] = Field(..., description="List of chats")
    total: int = Field(..., description="Total number of chats")
    limit: int = Field(..., description="Limit applied")
    offset: int = Field(..., description="Offset applied")
    has_more: bool = Field(..., description="Whether there are more results")

class ChatMessageResponse(BaseModel):
    """Chat message response"""
    id: str = Field(..., description="Message ID")
    chat_id: str = Field(..., description="Chat ID")
    role: MessageRole = Field(..., description="Message role")
    content: Dict[str, Any] = Field(..., description="Message content")
    model: Optional[str] = Field(None, description="Model used")
    tokens_in: Optional[int] = Field(None, description="Input tokens")
    tokens_out: Optional[int] = Field(None, description="Output tokens")
    meta: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    class Config:
        from_attributes = True

class ChatMessageListResponse(BaseModel):
    """Chat message list response"""
    messages: List[ChatMessageResponse] = Field(..., description="List of messages")
    total: int = Field(..., description="Total number of messages")
    limit: int = Field(..., description="Limit applied")
    cursor: Optional[str] = Field(None, description="Next cursor for pagination")
    has_more: bool = Field(..., description="Whether there are more results")

class ChatStatsResponse(BaseModel):
    """Chat statistics response"""
    chat_id: str = Field(..., description="Chat ID")
    name: Optional[str] = Field(None, description="Chat name")
    tags: List[str] = Field(default_factory=list, description="Chat tags")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_message_at: Optional[datetime] = Field(None, description="Last message timestamp")
    total_messages: int = Field(..., description="Total number of messages")
    user_messages: int = Field(..., description="Number of user messages")
    assistant_messages: int = Field(..., description="Number of assistant messages")

class ChatWithMessagesResponse(BaseModel):
    """Chat with messages response"""
    chat: ChatResponse = Field(..., description="Chat information")
    messages: List[ChatMessageResponse] = Field(..., description="Chat messages")
    total_messages: int = Field(..., description="Total number of messages")
    has_more: bool = Field(..., description="Whether there are more messages")
    next_cursor: Optional[str] = Field(None, description="Next cursor for pagination")

# Legacy schemas for backward compatibility
class ChatMessage(BaseModel):
    """Legacy chat message schema"""
    role: str = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")

class ChatTurnRequest(BaseModel):
    """Legacy chat turn request"""
    message: str = Field(..., description="User message")
    chat_id: Optional[str] = Field(None, description="Chat ID")
    model: Optional[str] = Field(None, description="Model to use")
    temperature: Optional[float] = Field(0.7, ge=0.0, le=2.0, description="Temperature")
    max_tokens: Optional[int] = Field(1000, ge=1, le=4000, description="Max tokens")
    idempotency_key: Optional[str] = Field(None, description="Idempotency key")

class ChatTurnResponse(BaseModel):
    """Legacy chat turn response"""
    message: str = Field(..., description="Assistant message")
    chat_id: str = Field(..., description="Chat ID")
    message_id: str = Field(..., description="Message ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    tokens_used: Optional[int] = Field(None, description="Tokens used")
