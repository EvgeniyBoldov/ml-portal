"""
RAG schemas and models
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.common import DocumentStatus, Step, IngestRunStatus, ChunkProfile, EmbeddingModel


class RAGDocumentBase(BaseModel):
    """Base RAG document schema matching RAGDocument model"""
    filename: str
    title: str
    name: Optional[str] = None
    content_type: Optional[str] = None
    source_mime: Optional[str] = None
    size: Optional[int] = None
    size_bytes: Optional[int] = None
    tags: Optional[List[str]] = Field(default=None)
    scope: str = "local"  # local or global


class RAGDocumentCreate(RAGDocumentBase):
    """RAG document creation schema"""
    tenant_id: Optional[UUID] = None
    user_id: UUID
    s3_key_raw: Optional[str] = None
    status: str = "uploaded"


class RAGDocumentUpdate(BaseModel):
    """RAG document update schema"""
    filename: Optional[str] = None
    title: Optional[str] = None
    name: Optional[str] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None
    scope: Optional[str] = None


class RAGDocumentResponse(RAGDocumentBase):
    """RAG document response schema matching RAGDocument model"""
    id: UUID
    tenant_id: Optional[UUID] = None
    uploaded_by: Optional[UUID] = None
    user_id: UUID
    status: str
    s3_key_raw: Optional[str] = None
    s3_key_processed: Optional[str] = None
    url_file: Optional[str] = None
    url_canonical_file: Optional[str] = None
    error: Optional[str] = None
    error_message: Optional[str] = None
    global_version: Optional[int] = None
    date_upload: datetime
    created_at: datetime
    updated_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    agg_status: Optional[str] = None
    agg_details_json: Optional[Dict[str, Any]] = None
    
    model_config = {"from_attributes": True}


class RAGChunkBase(BaseModel):
    """Base RAG chunk schema matching RAGChunk model"""
    document_id: UUID
    chunk_idx: int
    text: str
    embedding_model: Optional[str] = None
    embedding_version: Optional[str] = None
    meta: Optional[str] = None  # JSON string


class RAGChunkCreate(RAGChunkBase):
    """RAG chunk creation schema"""
    qdrant_point_id: Optional[UUID] = None


class RAGChunkResponse(RAGChunkBase):
    """RAG chunk response schema"""
    id: UUID
    qdrant_point_id: Optional[UUID] = None
    date_embedding: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


class EmbeddingMeta(BaseModel):
    """Embedding metadata schema"""
    document_id: UUID
    chunk_id: str
    model_alias: str
    model_version: str
    dimensions: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class IngestRunBase(BaseModel):
    """Base ingest run schema"""
    document_id: UUID
    tenant_id: UUID
    step: Step
    model_alias: Optional[str] = None
    attempt: int = 1
    status: IngestRunStatus
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IngestRunCreate(IngestRunBase):
    """Ingest run creation schema"""
    pass


class IngestRun(IngestRunBase):
    """Ingest run schema"""
    id: UUID
    started_at: datetime
    completed_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class IngestProgress(BaseModel):
    """Ingest progress schema"""
    document_id: UUID
    current_step: Step
    progress: float = Field(ge=0.0, le=100.0)
    completed_steps: List[Step] = Field(default_factory=list)
    failed_steps: List[Step] = Field(default_factory=list)
    models_processed: List[str] = Field(default_factory=list)
    total_chunks: int = 0
    processed_chunks: int = 0


class IngestRequest(BaseModel):
    """Ingest request schema"""
    document_id: UUID
    models: List[str] = Field(default_factory=lambda: ["all-MiniLM-L6-v2"])
    chunk_profile: ChunkProfile = ChunkProfile.BY_TOKENS
    force_reprocess: bool = False


class IngestResponse(BaseModel):
    """Ingest response schema"""
    document_id: UUID
    status: DocumentStatus
    progress: IngestProgress
    ingest_run_id: UUID