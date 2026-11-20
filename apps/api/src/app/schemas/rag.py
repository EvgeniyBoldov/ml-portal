"""
RAG schemas and models
"""
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.common import DocumentStatus, Step, ChunkProfile


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
