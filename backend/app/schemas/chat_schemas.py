from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from datetime import datetime
import uuid

class ChatCreateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255, description="Chat name")
    tags: Optional[List[str]] = Field(default_factory=list, description="Chat tags")
    
    @validator('tags')
    def validate_tags(cls, v):
        if v is None:
            return []
        # Ограничиваем количество тегов и их длину
        if len(v) > 20:
            raise ValueError('Too many tags (max 20)')
        for tag in v:
            if not isinstance(tag, str):
                raise ValueError('All tags must be strings')
            if len(tag) > 50:
                raise ValueError('Tag too long (max 50 characters)')
            if not tag.strip():
                raise ValueError('Empty tags not allowed')
        return [tag.strip() for tag in v if tag.strip()]

class ChatUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=255, description="New chat name")

class ChatTagsUpdateRequest(BaseModel):
    tags: List[str] = Field(..., description="Chat tags")
    
    @validator('tags')
    def validate_tags(cls, v):
        if len(v) > 20:
            raise ValueError('Too many tags (max 20)')
        for tag in v:
            if not isinstance(tag, str):
                raise ValueError('All tags must be strings')
            if len(tag) > 50:
                raise ValueError('Tag too long (max 50 characters)')
            if not tag.strip():
                raise ValueError('Empty tags not allowed')
        return [tag.strip() for tag in v if tag.strip()]

class ChatMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000, description="Message content")
    use_rag: bool = Field(False, description="Use RAG for response")
    response_stream: bool = Field(False, description="Stream response")
    
    @validator('content')
    def validate_content(cls, v):
        if not v.strip():
            raise ValueError('Message content cannot be empty')
        return v.strip()

class ChatResponse(BaseModel):
    id: str
    name: Optional[str]
    tags: List[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    last_message_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    
    class Config:
        from_attributes = True
