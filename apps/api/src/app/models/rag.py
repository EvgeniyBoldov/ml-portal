"""
RAG documents and chunks models
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from sqlalchemy import String, Integer, BigInteger, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID, ARRAY, ENUM, JSONB as PostgresJSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import event
from sqlalchemy.sql import func
import uuid

from .base import Base

class DocumentStatus(str, Enum):
    """Document processing status"""
    UPLOADED = "uploaded"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    PROCESSED = "processed"
    READY = "ready"
    FAILED = "failed"
    ARCHIVED = "archived"
    QUEUED = "queued"

class DocumentScope(str, Enum):
    """Document scope (local tenant or global)"""
    LOCAL = "local"
    GLOBAL = "global"

class RAGDocument(Base):
    """RAG documents table model"""
    __tablename__ = "ragdocuments"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)  # Required per migration
    
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    
    status: Mapped[str] = mapped_column(
        ENUM(
            'uploaded', 'uploading', 'processing', 'processed', 'ready', 'failed', 'archived', 'queued',
            name="documentstatus", create_type=False
        ),
        nullable=False,
        server_default="uploaded",
    )
    scope: Mapped[str] = mapped_column(
        ENUM('local', 'global', name="documentscope", create_type=False),
        nullable=False,
        server_default="local",
    )  # local or global
    
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_mime: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    
    s3_key_raw: Mapped[str | None] = mapped_column(String(500), nullable=True)
    s3_key_processed: Mapped[str | None] = mapped_column(String(500), nullable=True)
    url_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_canonical_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    tags: Mapped[List[str] | None] = mapped_column(ARRAY(String), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    global_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document_versions.id", ondelete="SET NULL"), nullable=True)  # TODO: add via migration if needed
    
    date_upload: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Aggregate status fields (from status aggregator)
    agg_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    agg_details_json: Mapped[Dict[str, Any] | None] = mapped_column(PostgresJSONB, nullable=True)  # JSONB in DB
    
    __table_args__ = (
        Index("ix_ragdocuments_tenant_id", "tenant_id"),
        Index("ix_ragdocuments_uploaded_by", "uploaded_by"),
        Index("ix_ragdocuments_status", "status"),
        Index("ix_ragdocuments_scope", "scope"),
    )


def _normalize_enum_fields(target: "RAGDocument") -> None:
    try:
        from enum import Enum as _Enum
        if isinstance(target.status, _Enum):
            target.status = target.status.value
        if isinstance(target.scope, _Enum):
            target.scope = target.scope.value
    except Exception:
        pass
    if isinstance(target.status, str):
        target.status = target.status.lower()
    if isinstance(target.scope, str):
        target.scope = target.scope.lower()


@event.listens_for(RAGDocument, "before_insert", propagate=True)
def _before_insert(mapper, connection, target: "RAGDocument"):
    _normalize_enum_fields(target)


@event.listens_for(RAGDocument, "before_update", propagate=True)
def _before_update(mapper, connection, target: "RAGDocument"):
    _normalize_enum_fields(target)

class RAGChunk(Base):
    """RAG chunks table model"""
    __tablename__ = "ragchunks"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=False)
    chunk_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    embedding_version: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_embedding: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[Dict[str, Any] | None] = mapped_column(String, nullable=True)  # JSON string
    qdrant_point_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    
    __table_args__ = (
        Index("ix_ragchunks_document_id", "document_id"),
        Index("ix_ragchunks_document_idx", "document_id", "chunk_idx"),
    )

