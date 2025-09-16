from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field, validator
from datetime import datetime
from enum import Enum

class RagStatus(str, Enum):
    UPLOADED = "uploaded"
    NORMALIZING = "normalizing"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    READY = "ready"
    ARCHIVED = "archived"
    DELETING = "deleting"
    ERROR = "error"

class RagDocumentUploadRequest(BaseModel):
    tags: Optional[List[str]] = Field(default_factory=list, description="Document tags")
    
    @validator('tags')
    def validate_tags(cls, v):
        if v is None:
            return []
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

class RagDocumentTagsUpdateRequest(BaseModel):
    tags: List[str] = Field(..., description="Document tags")
    
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

class RagSearchRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000, description="Search query")
    top_k: int = Field(10, ge=1, le=100, description="Number of results")
    min_score: float = Field(0.0, ge=0.0, le=1.0, description="Minimum similarity score")
    
    @validator('text')
    def validate_text(cls, v):
        if not v.strip():
            raise ValueError('Search text cannot be empty')
        return v.strip()

class RagDocumentResponse(BaseModel):
    id: str
    name: Optional[str]
    status: RagStatus
    date_upload: datetime
    url_file: Optional[str]
    url_canonical_file: Optional[str]
    tags: List[str]
    error: Optional[str]
    updated_at: Optional[datetime]
    progress: Optional[float] = None
    
    class Config:
        from_attributes = True

class RagSearchResult(BaseModel):
    id: str
    document_id: str
    text: str
    score: float
    snippet: str
    
    class Config:
        from_attributes = True

class RagMetricsResponse(BaseModel):
    total_documents: int
    total_chunks: int
    processing_documents: int
    storage_size_bytes: int
    storage_size_mb: float
    status_breakdown: dict
    ready_documents: int
    error_documents: int
