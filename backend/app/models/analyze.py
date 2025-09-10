from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Enum, Integer, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
import uuid

AnalyzeStatusEnum = Enum("queued", "processing", "done", "error", "canceled", name="analyze_status_enum", create_constraint=True)

class AnalysisDocuments(Base):
    __tablename__ = "analysisdocuments"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(AnalyzeStatusEnum, nullable=False, default="queued")
    date_upload: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    url_file: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url_canonical_file: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[List["AnalysisChunks"]] = relationship(back_populates="document", cascade="all, delete-orphan")

class AnalysisChunks(Base):
    __tablename__ = "analysischunks"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("analysisdocuments.id", ondelete="CASCADE"), nullable=False)
    chunk_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding_version: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    date_embedding: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    document: Mapped["AnalysisDocuments"] = relationship(back_populates="chunks")
