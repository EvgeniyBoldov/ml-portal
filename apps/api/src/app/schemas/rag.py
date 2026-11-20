"""
RAG schemas and models
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.schemas.common import DocumentStatus, Step, IngestRunStatus, ChunkProfile


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


class RAGChunkBase(BaseModel):
    """Base RAG chunk schema matching RAGChunk model"""
    document_id: UUID
    chunk_idx: int
    text: str
    embedding_model: Optional[str] = None
    embedding_version: Optional[str] = None
    meta: Optional[str] = None  # JSON string


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

    model_config = ConfigDict(protected_namespaces=())


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
    ingest_run_id: Optional[UUID] = None
