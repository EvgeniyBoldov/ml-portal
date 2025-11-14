"""
RAG ingest run schemas
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field

from app.schemas.common import Step, IngestRunStatus


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


class IngestRunUpdate(BaseModel):
    """Ingest run update schema"""
    status: Optional[IngestRunStatus] = None
    error_message: Optional[str] = None
    completed_at: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None


class IngestRunQuery(BaseModel):
    """Ingest run query schema"""
    document_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    step: Optional[Step] = None
    status: Optional[IngestRunStatus] = None
    model_alias: Optional[str] = None
    limit: int = Field(default=100, le=1000)
    offset: int = Field(default=0, ge=0)
