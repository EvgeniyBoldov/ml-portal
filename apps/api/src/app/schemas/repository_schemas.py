"""
Pydantic schemas for repository operations - replacing Dict[str, Any]
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
import uuid

from app.schemas.chats import MessageRole


class ChatCreateRequest(BaseModel):
    """Schema for creating a chat"""
    name: str = Field(..., min_length=1, max_length=255)
    tags: Optional[List[str]] = Field(default=None, max_length=10)
    
    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v):
        if v is not None:
            for tag in v:
                if len(tag) > 50:
                    raise ValueError('Tag too long')
        return v


class ChatMessageCreateRequest(BaseModel):
    """Schema for creating a chat message"""
    role: MessageRole
    content: Union[str, Dict[str, Any]] = Field(...)
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v):
        if isinstance(v, str):
            return {"text": v}
        elif isinstance(v, dict):
            if "text" not in v:
                raise ValueError("Content must contain 'text' field")
            return v
        else:
            raise ValueError("Content must be string or dict")


class RAGDocumentCreateRequest(BaseModel):
    """Schema for creating a RAG document"""
    filename: str = Field(..., min_length=1, max_length=255)
    title: Optional[str] = Field(default=None, max_length=255)
    content_type: Optional[str] = Field(default=None, max_length=100)
    size: Optional[int] = Field(default=None, ge=0)
    tags: Optional[List[str]] = Field(default=None, max_items=10)
    url_file: Optional[str] = Field(default=None, max_length=500)
    status: str = Field(default="uploading", max_length=50)


class RAGChunkCreateRequest(BaseModel):
    """Schema for creating a RAG chunk"""
    content: str = Field(..., min_length=1)
    chunk_idx: int = Field(..., ge=0)
    embedding: Optional[List[float]] = Field(default=None)
    vector_id: Optional[str] = Field(default=None, max_length=255)
    meta: Optional[Dict[str, Any]] = Field(default=None)


class AuditLogCreateRequest(BaseModel):
    """Schema for creating an audit log"""
    action: str = Field(..., min_length=1, max_length=100)
    actor_user_id: Optional[uuid.UUID] = Field(default=None)
    object_type: Optional[str] = Field(default=None, max_length=50)
    object_id: Optional[str] = Field(default=None, max_length=255)
    meta: Optional[Dict[str, Any]] = Field(default=None)
    ip: Optional[str] = Field(default=None, max_length=45)  # IPv6 max length
    user_agent: Optional[str] = Field(default=None, max_length=500)
    request_id: Optional[str] = Field(default=None, max_length=255)


class IdempotencyKeyCreateRequest(BaseModel):
    """Schema for creating an idempotency key"""
    key: str = Field(..., min_length=1, max_length=255)
    method: str = Field(..., min_length=1, max_length=10)
    path: str = Field(..., min_length=1, max_length=500)
    body: Optional[Dict[str, Any]] = Field(default=None)
    response_status: int = Field(..., ge=100, le=599)
    response_body: Optional[Dict[str, Any]] = Field(default=None)
    response_headers: Optional[Dict[str, str]] = Field(default=None)
    ttl_at: datetime = Field(...)


class ChatUpdateRequest(BaseModel):
    """Schema for updating a chat"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    tags: Optional[List[str]] = Field(default=None, max_length=10)
    last_message_at: Optional[datetime] = Field(default=None)
    
    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v):
        if v is not None:
            for tag in v:
                if len(tag) > 50:
                    raise ValueError('Tag too long')
        return v


class RAGDocumentUpdateRequest(BaseModel):
    """Schema for updating a RAG document"""
    title: Optional[str] = Field(default=None, max_length=255)
    status: Optional[str] = Field(default=None, max_length=50)
    url_file: Optional[str] = Field(default=None, max_length=500)
    error_message: Optional[str] = Field(default=None, max_length=1000)
    processed_at: Optional[datetime] = Field(default=None)


class FilterRequest(BaseModel):
    """Schema for repository filters"""
    filters: Optional[Dict[str, Any]] = Field(default=None)
    order_by: Optional[str] = Field(default=None, max_length=100)
    limit: int = Field(default=100, ge=1, le=1000)
    cursor: Optional[str] = Field(default=None, max_length=500)
    include_relations: Optional[List[str]] = Field(default=None, max_items=10)


class PaginationRequest(BaseModel):
    """Schema for pagination parameters"""
    limit: int = Field(default=100, ge=1, le=1000)
    cursor: Optional[str] = Field(default=None, max_length=500)


class SearchRequest(BaseModel):
    """Schema for search operations"""
    query: str = Field(..., min_length=1, max_length=500)
    k: int = Field(default=5, ge=1, le=100)
    filters: Optional[Dict[str, Any]] = Field(default=None)


class BulkCreateRequest(BaseModel):
    """Schema for bulk create operations"""
    items: List[Dict[str, Any]] = Field(..., min_length=1, max_length=1000)
    
    @field_validator('items')
    @classmethod
    def validate_items(cls, v):
        if len(v) > 1000:
            raise ValueError('Too many items for bulk operation')
        return v


class BulkUpdateRequest(BaseModel):
    """Schema for bulk update operations"""
    updates: List[Dict[str, Any]] = Field(..., min_length=1, max_length=1000)
    
    @field_validator('updates')
    @classmethod
    def validate_updates(cls, v):
        if len(v) > 1000:
            raise ValueError('Too many updates for bulk operation')
        return v


# Response schemas
class ChatResponse(BaseModel):
    """Schema for chat response"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    tags: Optional[List[str]]
    version: int
    created_at: datetime
    updated_at: datetime
    last_message_at: Optional[datetime]
    
    model_config = {"from_attributes": True}


class ChatMessageResponse(BaseModel):
    """Schema for chat message response"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    chat_id: uuid.UUID
    role: MessageRole
    content: Union[str, Dict[str, Any]]
    version: int
    created_at: datetime
    updated_at: datetime
    meta: Optional[Dict[str, Any]]
    
    model_config = {"from_attributes": True}


class RAGDocumentResponse(BaseModel):
    """Schema for RAG document response"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    uploaded_by: uuid.UUID
    filename: str
    title: str
    content_type: Optional[str]
    size: Optional[int]
    tags: List[str]
    url_file: Optional[str]
    status: str
    error_message: Optional[str]
    version: int
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime]
    
    model_config = {"from_attributes": True}


class RAGChunkResponse(BaseModel):
    """Schema for RAG chunk response"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    chunk_idx: int
    embedding: Optional[List[float]]
    vector_id: Optional[str]
    meta: Optional[Dict[str, Any]]
    version: int
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class AuditLogResponse(BaseModel):
    """Schema for audit log response"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    actor_user_id: Optional[uuid.UUID]
    action: str
    object_type: Optional[str]
    object_id: Optional[str]
    meta: Optional[Dict[str, Any]]
    ip: Optional[str]
    user_agent: Optional[str]
    request_id: Optional[str]
    created_at: datetime
    
    model_config = {"from_attributes": True}


class IdempotencyKeyResponse(BaseModel):
    """Schema for idempotency key response"""
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: Optional[uuid.UUID]
    key: str
    req_hash: str
    response_status: int
    response_body: Optional[Dict[str, Any]]
    response_headers: Optional[Dict[str, str]]
    ttl_at: datetime
    created_at: datetime
    
    model_config = {"from_attributes": True}


class PaginatedResponse(BaseModel):
    """Schema for paginated responses"""
    items: List[Any]
    next_cursor: Optional[str]
    total: Optional[int] = None
    has_more: bool = False


class RepositoryStatsResponse(BaseModel):
    """Schema for repository statistics"""
    total: int
    active: int
    expired: Optional[int] = None
    failed: Optional[int] = None
