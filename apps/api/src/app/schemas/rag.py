"""
RAG schemas for API v1
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

class RAGUploadRequest(BaseModel):
    """Request schema for RAG upload"""
    name: str = Field(..., min_length=1, max_length=255, description="Document name")
    mime: str = Field(..., description="MIME type")
    size: int = Field(..., gt=0, le=50*1024*1024, description="File size in bytes")
    tags: List[str] = Field(default_factory=list, description="Document tags")
    options: Dict[str, Any] = Field(default_factory=dict, description="Upload options")

class RAGUploadResponse(BaseModel):
    """Response schema for RAG upload"""
    source_id: str = Field(..., description="Document ID")
    upload: Dict[str, Any] = Field(..., description="Upload information")

class RAGSearchRequest(BaseModel):
    """Request schema for RAG search"""
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    limit: int = Field(10, ge=1, le=100, description="Maximum results")
    offset: int = Field(0, ge=0, description="Results offset")
    filters: Optional[Dict[str, Any]] = Field(None, description="Search filters")

class RAGSearchResponse(BaseModel):
    """Response schema for RAG search"""
    results: List[Dict[str, Any]] = Field(..., description="Search results")
    total: int = Field(..., description="Total results count")
    query: str = Field(..., description="Search query")