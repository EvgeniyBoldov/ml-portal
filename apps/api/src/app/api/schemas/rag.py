"""
RAG-related API schemas
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from enum import Enum

class RAGDocumentStatus(str, Enum):
    """RAG document status"""
    UPLOADING = "uploading"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    ARCHIVED = "archived"

# Request schemas
class RAGDocumentCreateRequest(BaseModel):
    """RAG document creation request"""
    filename: str = Field(..., min_length=1, max_length=255, description="Document filename")
    title: str = Field(..., min_length=1, max_length=500, description="Document title")
    content_type: Optional[str] = Field(None, max_length=100, description="Content type")
    size: Optional[int] = Field(None, ge=0, description="File size in bytes")
    tags: Optional[List[str]] = Field(default_factory=list, description="Document tags")
    
    @field_validator('filename')
    @classmethod
    def validate_filename(cls, v):
        if not v or not v.strip():
            raise ValueError('Filename cannot be empty')
        return v.strip()
    
    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if not v or not v.strip():
            raise ValueError('Title cannot be empty')
        return v.strip()
    
    @field_validator('tags')
    @classmethod
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

class RAGDocumentUpdateRequest(BaseModel):
    """RAG document update request"""
    title: Optional[str] = Field(None, min_length=1, max_length=500, description="New title")
    tags: Optional[List[str]] = Field(None, description="New tags")
    
    @field_validator('title')
    @classmethod
    def validate_title(cls, v):
        if v is not None and not v.strip():
            return None
        return v.strip() if v else None
    
    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v):
        if v is None:
            return None
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

class RAGDocumentSearchRequest(BaseModel):
    """RAG document search request"""
    query: str = Field(..., min_length=2, max_length=100, description="Search query")
    status: Optional[RAGDocumentStatus] = Field(None, description="Filter by status")
    tag: Optional[str] = Field(None, min_length=1, max_length=50, description="Filter by tag")
    limit: int = Field(50, ge=1, le=100, description="Number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")

class RAGDocumentListRequest(BaseModel):
    """RAG document list request"""
    status: Optional[RAGDocumentStatus] = Field(None, description="Filter by status")
    limit: int = Field(50, ge=1, le=100, description="Number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")

class RAGChunkCreateRequest(BaseModel):
    """RAG chunk creation request"""
    content: str = Field(..., min_length=1, max_length=10000, description="Chunk content")
    chunk_index: int = Field(..., ge=0, description="Chunk index")
    embedding: Optional[List[float]] = Field(None, description="Chunk embedding")
    vector_id: Optional[str] = Field(None, max_length=255, description="Vector ID")
    chunk_metadata: Optional[Dict[str, Any]] = Field(None, description="Chunk metadata")
    
    @field_validator('content')
    @classmethod
    def validate_content(cls, v):
        if not v or not v.strip():
            raise ValueError('Content cannot be empty')
        return v.strip()

class RAGChunkSearchRequest(BaseModel):
    """RAG chunk search request"""
    query: str = Field(..., min_length=2, max_length=100, description="Search query")
    limit: int = Field(50, ge=1, le=100, description="Number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")

class RAGSearchRequest(BaseModel):
    """RAG search request"""
    query: str = Field(..., min_length=2, max_length=200, description="Search query")
    top_k: int = Field(10, ge=1, le=100, description="Number of results")
    filters: Optional[Dict[str, Any]] = Field(None, description="Search filters")
    with_snippets: bool = Field(True, description="Include snippets")
    rrf_rank: int = Field(60, ge=1, le=1000, description="RRF rank parameter")
    
    @field_validator('query')
    @classmethod
    def validate_query(cls, v):
        if not v or not v.strip():
            raise ValueError('Query cannot be empty')
        return v.strip()

# Response schemas
class RAGDocumentResponse(BaseModel):
    """RAG document response"""
    id: str = Field(..., description="Document ID")
    filename: str = Field(..., description="Document filename")
    title: str = Field(..., description="Document title")
    content_type: Optional[str] = Field(None, description="Content type")
    size: Optional[int] = Field(None, description="File size in bytes")
    tags: List[str] = Field(default_factory=list, description="Document tags")
    status: RAGDocumentStatus = Field(..., description="Document status")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    s3_key_raw: Optional[str] = Field(None, description="S3 key for raw file")
    s3_key_processed: Optional[str] = Field(None, description="S3 key for processed file")
    user_id: str = Field(..., description="Owner user ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    processed_at: Optional[datetime] = Field(None, description="Processing completion timestamp")
    
    class Config:
        from_attributes = True

class RAGDocumentListResponse(BaseModel):
    """RAG document list response"""
    documents: List[RAGDocumentResponse] = Field(..., description="List of documents")
    total: int = Field(..., description="Total number of documents")
    limit: int = Field(..., description="Limit applied")
    offset: int = Field(..., description="Offset applied")
    has_more: bool = Field(..., description="Whether there are more results")

class RAGDocumentStatsResponse(BaseModel):
    """RAG document statistics response"""
    total: int = Field(..., description="Total documents")
    processed: int = Field(..., description="Processed documents")
    processing: int = Field(..., description="Processing documents")
    failed: int = Field(..., description="Failed documents")

class RAGChunkResponse(BaseModel):
    """RAG chunk response"""
    id: str = Field(..., description="Chunk ID")
    document_id: str = Field(..., description="Document ID")
    content: str = Field(..., description="Chunk content")
    chunk_index: int = Field(..., description="Chunk index")
    embedding: Optional[List[float]] = Field(None, description="Chunk embedding")
    vector_id: Optional[str] = Field(None, description="Vector ID")
    chunk_metadata: Dict[str, Any] = Field(default_factory=dict, description="Chunk metadata")
    created_at: datetime = Field(..., description="Creation timestamp")
    
    class Config:
        from_attributes = True

class RAGChunkListResponse(BaseModel):
    """RAG chunk list response"""
    chunks: List[RAGChunkResponse] = Field(..., description="List of chunks")
    total: int = Field(..., description="Total number of chunks")
    limit: int = Field(..., description="Limit applied")
    offset: int = Field(..., description="Offset applied")
    has_more: bool = Field(..., description="Whether there are more results")

class RAGChunkStatsResponse(BaseModel):
    """RAG chunk statistics response"""
    document_id: str = Field(..., description="Document ID")
    total_chunks: int = Field(..., description="Total chunks")
    chunks_with_embeddings: int = Field(..., description="Chunks with embeddings")
    chunks_without_embeddings: int = Field(..., description="Chunks without embeddings")

class RAGSearchResult(BaseModel):
    """RAG search result"""
    id: str = Field(..., description="Chunk ID")
    document_id: str = Field(..., description="Document ID")
    content: str = Field(..., description="Chunk content")
    score: float = Field(..., description="Relevance score")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Result metadata")
    snippet: Optional[str] = Field(None, description="Content snippet")

class RAGSearchResponse(BaseModel):
    """RAG search response"""
    results: List[RAGSearchResult] = Field(..., description="Search results")
    total: int = Field(..., description="Total number of results")
    query: str = Field(..., description="Search query")
    search_time_ms: float = Field(..., description="Search time in milliseconds")
    models_used: List[str] = Field(default_factory=list, description="Models used")

class RAGUploadResponse(BaseModel):
    """RAG upload response"""
    document_id: str = Field(..., description="Document ID")
    upload_url: str = Field(..., description="Presigned upload URL")
    s3_key: str = Field(..., description="S3 key")
    expires_in: int = Field(..., description="URL expiration in seconds")

# Legacy schemas for backward compatibility
class RagDocument(BaseModel):
    """Legacy RAG document schema"""
    id: str = Field(..., description="Document ID")
    filename: str = Field(..., description="Document filename")
    title: str = Field(..., description="Document title")
    status: str = Field(..., description="Document status")
    created_at: datetime = Field(..., description="Creation timestamp")

class RagUploadRequest(BaseModel):
    """Legacy RAG upload request"""
    url: Optional[str] = Field(None, description="Document URL")
    title: Optional[str] = Field(None, description="Document title")
    tags: Optional[List[str]] = Field(None, description="Document tags")
