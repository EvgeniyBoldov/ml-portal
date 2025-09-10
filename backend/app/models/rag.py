from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from sqlalchemy import String, Text, DateTime, Enum, Integer, BigInteger, ARRAY, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base
import uuid

RagStatusEnum = Enum(
    "uploaded", "normalizing", "chunking", "embedding", "indexing", "ready", "archived", "deleting", "error",
    name="rag_status_enum",
    create_constraint=True
)

class RagDocuments(Base):
    __tablename__ = "ragdocuments"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(RagStatusEnum, nullable=False, default="uploaded")
    date_upload: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", nullable=False)
    uploaded_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    url_file: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url_canonical_file: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_mime: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(String), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks: Mapped[List["RagChunks"]] = relationship(back_populates="document", cascade="all, delete-orphan")

class RagChunks(Base):
    __tablename__ = "ragchunks"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=False)
    chunk_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding_version: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    date_embedding: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    qdrant_point_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    document: Mapped["RagDocuments"] = relationship(back_populates="chunks")
