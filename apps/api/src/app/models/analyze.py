from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Enum, Integer, JSON, ForeignKey, Index
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
import uuid

AnalyzeStatusEnum = Enum("queued", "processing", "done", "error", "canceled", name="analyze_status_enum", create_constraint=True)

class AnalysisDocuments(Base):
    __tablename__ = "analysisdocuments"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(AnalyzeStatusEnum, nullable=False, default="queued")
    date_upload: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    url_file: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url_canonical_file: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[List["AnalysisChunks"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    
    # Composite indexes for multi-tenant queries and JSONB search
    __table_args__ = (
        Index("ix_analysisdocuments_tenant_created", "tenant_id", "date_upload"),
        Index("ix_analysisdocuments_tenant_status", "tenant_id", "status"),
        Index("ix_analysisdocuments_result_gin", "result", postgresql_using="gin"),
    )

class AnalysisChunks(Base):
    __tablename__ = "analysischunks"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analysisdocuments.id", ondelete="CASCADE"), nullable=False)
    chunk_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding_version: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    date_embedding: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    document: Mapped["AnalysisDocuments"] = relationship(back_populates="chunks")
    
    # Composite indexes for multi-tenant queries and JSONB search
    __table_args__ = (
        Index("ix_analysischunks_tenant_document", "tenant_id", "document_id"),
        Index("ix_analysischunks_tenant_idx", "tenant_id", "chunk_idx"),
        Index("ix_analysischunks_meta_gin", "meta", postgresql_using="gin"),
    )
