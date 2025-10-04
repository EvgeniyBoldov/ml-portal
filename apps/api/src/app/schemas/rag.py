"""
RAG Document schemas with RBAC and Scoping
"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field
from app.models.rag import DocumentScope, DocumentStatus


class DocumentScopeEnum(str, Enum):
    """Document scope options"""
    LOCAL = DocumentScope.LOCAL.value
    GLOBAL = DocumentScope.GLOBAL.value


class DocumentStatusEnum(str, Enum):
    """Document status options"""
    UPLOADING = DocumentStatus.UPLOADING.value
    PROCESSING = DocumentStatus.PROCESSING.value
    PROCESSED = DocumentStatus.PROCESSED.value
    FAILED = DocumentStatus.FAILED.value
    ARCHIVED = DocumentStatus.ARCHIVED.value


class RAGDocumentCreate(BaseModel):
    """Schema for creating RAG documents"""
    filename: str = Field(..., min_length=1, max_length=255, description="Document filename")
    title: str = Field(..., min_length=1, max_length=255, description="Document title")
    content_type: Optional[str] = Field(None, description="MIME content type")
    size: Optional[int] = Field(None, ge=0, description="File size in bytes")
    tags: Optional[List[str]] = Field(default=[], description="Document tags")
    
    # RBAC and Scoping
    scope: DocumentScopeEnum = Field(default=DocumentScopeEnum.LOCAL, description="Document scope")
    tenant_id: Optional[UUID] = Field(None, description="Target tenant (required for local docs)")

    class Config:
        json_schema_extra = {
            "example": {
                "filename": "document.pdf",
                "title": "Important Document",
                "content_type": "application/pdf",
                "size": 1024000,
                "tags": ["important", "legal"],
                "scope": "local",
                "tenant_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }


class RAGDocumentUpdate(BaseModel):
    """Schema for updating RAG documents"""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    tags: Optional[List[str]] = None
    scope: Optional[DocumentScopeEnum] = None
    tenant_id: Optional[UUID] = None

    class Config:
        validate_assignment = True


class RAGDocumentResponse(BaseModel):
    """Schema for RAG document responses"""
    id: str = Field(..., description="Document ID")
    filename: str = Field(..., description="Document filename")
    title: str = Field(..., description="Document title")
    status: str = Field(..., description="Processing status")
    
    # RBAC and Scoping
    scope: str = Field(..., description="Document scope")
    tenant_id: Optional[str] = Field(None, description="Tenant ID (null for global)")
    
    # Ownership
    user_id: str = Field(..., description="Document owner user ID")
    
    # Versioning (for global documents)
    global_version: Optional[int] = Field(None, description="Version for global documents")
    published_at: Optional[datetime] = Field(None, description="Global document publication time")
    published_by: Optional[str] = Field(None, description="User who published global document")
    
    # Metadata
    content_type: Optional[str] = Field(None, description="MIME content type")
    size: Optional[int] = Field(None, description="File size in bytes")
    tags: List[str] = Field(default=[], description="Document tags")
    
    # Storage
    s3_key_raw: Optional[str] = Field(None, description="S3 key for raw file")
    s3_key_processed: Optional[str] = Field(None, description="S3 key for processed file")
    
    # Timestamps
    created_at: datetime = Field(..., description="Creation time")
    updated_at: datetime = Field(..., description="Last update time")
    processed_at: Optional[datetime] = Field(None, description="Processing completion time")
    
    # Errors
    error_message: Optional[str] = Field(None, description="Processing error message")

    class Config:
        from_attributes = True


class RAGDocumentListResponse(BaseModel):
    """Schema for paginated document list responses"""
    documents: List[RAGDocumentResponse] = Field(..., description="List of documents")
    total: int = Field(..., description="Total number of documents")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Page size")
    has_next: bool = Field(..., description="Whether there are more pages")


class RAGSearchRequest(BaseModel):
    """Schema for RAG search requests"""
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    limit: int = Field(default=10, ge=1, le=100, description="Number of results to return")
    threshold: float = Field(default=0.7, ge=0.0, le=1.0, description="Similarity threshold")
    include_local: bool = Field(default=True, description="Include local documents")
    include_global: bool = Field(default=True, description="Include global documents")
    
    # Optional filtering
    tags: Optional[List[str]] = Field(None, description="Filter by document tags")
    exclude_tenant_id: Optional[UUID] = Field(None, description="Exclude specific tenant documents")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "machine learning algorithms",
                "limit": 10,
                "threshold": 0.8,
                "include_local": True,
                "include_global": True,
                "tags": ["ml", "tutorial"]
            }
        }


class RAGSearchResult(BaseModel):
    """Schema for RAG search results"""
    document_id: str = Field(..., description="Document ID")
    chunk_id: str = Field(..., description="Chunk ID") 
    content: str = Field(..., description="Chunk content")
    score: float = Field(..., description="Similarity score")
    
    # Document metadata
    document_title: str = Field(..., description="Document title")
    document_filename: str = Field(..., description="Document filename")
    document_scope: str = Field(..., description="Document scope")
    document_tenant_id: Optional[str] = Field(None, description="Document tenant ID")
    
    # Chunk metadata
    chunk_index: int = Field(..., description="Chunk index in document")
    chunk_metadata: Dict[str, Any] = Field(default=dict, description="Additional chunk metadata")


class RAGSearchResponse(BaseModel):
    """Schema for RAG search responses"""
    results: List[RAGSearchResult] = Field(..., description="Search results")
    total: int = Field(..., description="Total number of found chunks")
    query: str = Field(..., description="Original search query")
    processing_time: float = Field(..., description="Search processing time in seconds")


class ReindexRequest(BaseModel):
    """Schema for reindex requests"""
    trigger_type: str = Field(..., description="Type of reindex trigger")
    
    # Target selection (all fields optional for full reindex)
    tenant_id: Optional[UUID] = Field(None, description="Specific tenant to reindex") 
    document_id: Optional[UUID] = Field(None, description="Specific document to reindex")
    scope: Optional[DocumentScopeEnum] = Field(None, description="Documents with specific scope")
    
    # Processing options
    force: bool = Field(default=False, description="Force reindex even if already processed")
    incremental: bool = Field(default=True, description="Perform incremental reindex")

    class Config:
        json_schema_extra = {
            "example": {
                "trigger_type": "full",
                "scope": "global",
                "force": False,
                "incremental": True
            }
        }


class ReindexResponse(BaseModel):
    """Schema for reindex responses"""
    job_id: str = Field(..., description="Reindex job ID")
    status: str = Field(..., description="Job status")
    trigger_type: str = Field(..., description="Trigger type")
    
    # Target info
    tenant_id: Optional[str] = Field(None, description="Target tenant")
    document_id: Optional[str] = Field(None, description="Target document")
    scope: Optional[str] = Field(None, description="Target scope")
    
    # Processing stats
    documents_processed: int = Field(default=0, description="Documents processed")
    chunks_processed: int = Field(default=0, description="Chunks processed")
    
    # Progress info
    progress_percentage: float = Field(default=0.0, ge=0.0, le=100.0, description="Progress percentage")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")
    
    # Timestamps
    started_at: datetime = Field(..., description="Job start time")
    completed_at: Optional[datetime] = Field(None, description="Job completion time")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class ReindexStatus(BaseModel):
    """Schema for checking reindex job status"""
    job_id: str = Field(..., description="Job ID")
    status: str = Field(..., description="Job status: pending, running, completed, failed")
    
    # Progress info
    progress_percentage: float = Field(default=0.0, description="Progress percentage")
    current_document: Optional[str] = Field(None, description="Currently processing document")
    documents_processed: int = Field(default=0, description="Documents processed")
    chunks_processed: int = Field(default=0, description="Chunks processed")
    
    # Timestamps
    started_at: datetime = Field(..., description="Job start time")
    estimated_completion: Optional[datetime] = Field(None, description="Estimated completion time")
    completed_at: Optional[datetime] = Field(None, description="Job completion time")
    
    # Error info
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_details: Optional[Dict[str, Any]] = Field(None, description="Detailed error information")