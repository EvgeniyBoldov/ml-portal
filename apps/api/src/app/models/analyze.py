"""
Analysis documents and chunks models
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import uuid

from .base import Base

class AnalysisDocuments(Base):
    """Analysis documents table model"""
    __tablename__ = "analysisdocuments"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="uploaded")
    date_upload: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    url_file: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_mime: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, onupdate=func.now())
    
    # Relationships
    chunks = relationship("AnalysisChunks", back_populates="document", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("ix_analysisdocuments_uploaded_by", "uploaded_by"),
        Index("ix_analysisdocuments_status", "status"),
    )

class AnalysisChunks(Base):
    """Analysis chunks table model"""
    __tablename__ = "analysischunks"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analysisdocuments.id", ondelete="CASCADE"), nullable=False)
    chunk_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[Dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    
    # Relationships
    document = relationship("AnalysisDocuments", back_populates="chunks")
    
    __table_args__ = (
        Index("ix_analysischunks_document_id", "document_id"),
        Index("ix_analysischunks_document_idx", "document_id", "chunk_idx"),
    )

