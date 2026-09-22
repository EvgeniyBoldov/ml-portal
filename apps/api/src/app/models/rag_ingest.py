# app/models/rag_ingest.py
from __future__ import annotations
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from .base import Base

class Source(Base):
    """Таблица sources для хранения метаданных документов в ingest pipeline
    
    Статус документа хранится в RAGDocument.status, не здесь.
    """
    __tablename__ = 'sources'
    
    source_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey('tenants.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    meta = Column(JSONB, nullable=True)
    
    # Связи
    chunks = relationship("Chunk", back_populates="source", cascade="all, delete-orphan")
    emb_statuses = relationship("EmbStatus", back_populates="source", cascade="all, delete-orphan")
    collection_memberships = relationship(
        "DocumentCollectionMembership",
        back_populates="source",
        cascade="all, delete-orphan",
    )
    
    # Ограничения
    __table_args__ = (
        Index('ix_sources_updated_at', 'updated_at'),
        Index('ix_sources_tenant_id', 'tenant_id'),
    )


class DocumentCollectionMembership(Base):
    """Explicit document-to-collection membership contract."""

    __tablename__ = "document_collection_memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.source_id", ondelete="CASCADE"), nullable=False)
    collection_id = Column(UUID(as_uuid=True), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False)
    collection_row_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    source = relationship("Source", back_populates="collection_memberships")

    __table_args__ = (
        UniqueConstraint("source_id", "collection_id", name="uq_doc_collection_membership"),
        Index("ix_doc_coll_memberships_tenant", "tenant_id"),
        Index("ix_doc_coll_memberships_collection", "collection_id"),
        Index("ix_doc_coll_memberships_source", "source_id"),
    )

class Chunk(Base):
    """Таблица chunks для хранения информации о чанках документов"""
    __tablename__ = 'chunks'
    
    chunk_id = Column(Text, primary_key=True)
    source_id = Column(UUID(as_uuid=True), ForeignKey('sources.source_id', ondelete='CASCADE'), nullable=False)
    page = Column(Integer, nullable=True)
    offset = Column(Integer, nullable=False)
    length = Column(Integer, nullable=False)
    lang = Column(Text, nullable=True)
    hash = Column(Text, nullable=False)
    meta = Column(JSONB, nullable=True)
    
    # Связи
    source = relationship("Source", back_populates="chunks")
    
    # Ограничения
    __table_args__ = (
        UniqueConstraint('source_id', 'offset', name='uq_chunks_source_offset'),
        Index('ix_chunks_source_id', 'source_id'),
        Index('ix_chunks_hash', 'hash'),
    )

class EmbStatus(Base):
    """Таблица emb_status для отслеживания прогресса эмбеддингов по моделям"""
    __tablename__ = 'emb_status'
    
    source_id = Column(UUID(as_uuid=True), ForeignKey('sources.source_id', ondelete='CASCADE'), nullable=False, primary_key=True)
    model_alias = Column(Text, nullable=False, primary_key=True)
    done_count = Column(Integer, nullable=False, default=0)
    total_count = Column(Integer, nullable=False, default=0)
    model_version = Column(Text, nullable=True)
    last_error = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Связи
    source = relationship("Source", back_populates="emb_statuses")
    
    # Ограничения
    __table_args__ = (
        Index('ix_emb_status_source_id', 'source_id'),
        Index('ix_emb_status_model_alias', 'model_alias'),
    )

class RAGStatus(Base):
    """Таблица rag_statuses для отслеживания статусов узлов графа pipeline и embedding"""
    __tablename__ = 'rag_statuses'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id = Column(UUID(as_uuid=True), ForeignKey('ragdocuments.id', ondelete='CASCADE'), nullable=False)
    node_type = Column(String(20), nullable=False)  # 'pipeline' | 'embedding' | 'index'
    node_key = Column(String(100), nullable=False)  # 'upload'|'extract'|'normalize'|'chunk' OR model_alias
    status = Column(String(20), nullable=False)  # 'pending'|'queued'|'processing'|'completed'|'failed'|'cancelled'
    celery_task_id = Column(String(50), nullable=True)  # For task cancellation
    model_version = Column(String(50), nullable=True)
    modality = Column(String(20), nullable=True)  # 'text'|'image'
    error_short = Column(Text, nullable=True)
    metrics_json = Column(JSONB, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    
    # Ограничения
    __table_args__ = (
        UniqueConstraint('doc_id', 'node_type', 'node_key', name='uq_rag_statuses_doc_node'),
        Index('ix_rag_statuses_doc_id', 'doc_id'),
        Index('ix_rag_statuses_status', 'status'),
        Index('ix_rag_statuses_node_type', 'node_type'),
        Index('ix_rag_statuses_updated_at', 'updated_at'),
    )


class RAGIngestRun(Base):
    """A durable, fenced execution of the document ingest state machine.

    Celery task ids are deliberately not the source of truth here: a broker can
    accept a message before the request transaction commits, or lose a message
    after it commits.  A run is created in the same transaction as its outbox
    command and carries a monotonically increasing generation for the document.
    """

    __tablename__ = "rag_ingest_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_id = Column(UUID(as_uuid=True), ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    generation = Column(Integer, nullable=False)
    trigger = Column(String(32), nullable=False)
    status = Column(String(20), nullable=False, server_default="queued")
    target_models = Column(JSONB, nullable=False, server_default="[]")
    resume_stage = Column(String(64), nullable=True)
    error_short = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("doc_id", "generation", name="uq_rag_ingest_runs_doc_generation"),
        Index("ix_rag_ingest_runs_doc_id", "doc_id"),
        Index("ix_rag_ingest_runs_status", "status"),
    )


class RAGIngestOutbox(Base):
    """Transactional command to dispatch a durable ingest run to Celery."""

    __tablename__ = "rag_ingest_outbox"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("rag_ingest_runs.id", ondelete="CASCADE"), nullable=False)
    command = Column(String(32), nullable=False)
    payload = Column(JSONB, nullable=False, server_default="{}")
    status = Column(String(20), nullable=False, server_default="pending")
    attempts = Column(Integer, nullable=False, server_default="0")
    celery_task_id = Column(String(64), nullable=True)
    last_error = Column(Text, nullable=True)
    available_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("run_id", name="uq_rag_ingest_outbox_run"),
        Index("ix_rag_ingest_outbox_status_available", "status", "available_at"),
    )


class RAGIngestStageRun(Base):
    """Durable input/output record for one forward ingest stage."""

    __tablename__ = "rag_ingest_stage_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("rag_ingest_runs.id", ondelete="CASCADE"), nullable=False)
    stage_key = Column(String(128), nullable=False)
    status = Column(String(20), nullable=False, server_default="pending")
    celery_task_id = Column(String(64), nullable=True)
    input_fingerprint = Column(String(128), nullable=True)
    output_fingerprint = Column(String(128), nullable=True)
    result_json = Column(JSONB, nullable=True)
    metrics_json = Column(JSONB, nullable=True)
    error_short = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("run_id", "stage_key", name="uq_rag_ingest_stage_runs_run_stage"),
        Index("ix_rag_ingest_stage_runs_run", "run_id"),
        Index("ix_rag_ingest_stage_runs_status", "status"),
    )


class RAGIngestStageOutbox(Base):
    """One durable dispatch command per stage of an ingest run."""

    __tablename__ = "rag_ingest_stage_outbox"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("rag_ingest_runs.id", ondelete="CASCADE"), nullable=False)
    stage_key = Column(String(128), nullable=False)
    payload = Column(JSONB, nullable=False, server_default="{}")
    status = Column(String(20), nullable=False, server_default="pending")
    attempts = Column(Integer, nullable=False, server_default="0")
    celery_task_id = Column(String(64), nullable=True)
    last_error = Column(Text, nullable=True)
    available_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("run_id", "stage_key", name="uq_rag_ingest_stage_outbox_run_stage"),
        Index("ix_rag_ingest_stage_outbox_status_available", "status", "available_at"),
    )
