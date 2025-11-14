"""
State Engine models: document versions, jobs, status history, events outbox
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import Column, String, Integer, BigInteger, DateTime, Text, ForeignKey, Index, UniqueConstraint, Sequence
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
import uuid

from app.models.base import Base


class DocumentVersion(Base):
    """Document version tracking"""
    __tablename__ = "document_versions"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('ragdocuments.id', ondelete='CASCADE'),
        nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, comment='SHA256 hash of content')
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False, comment='S3 URI or path')
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    
    __table_args__ = (
        UniqueConstraint('document_id', 'content_hash', name='uq_doc_versions_doc_hash'),
        Index('ix_document_versions_document_id', 'document_id'),
        Index('ix_document_versions_content_hash', 'content_hash'),
    )


class Job(Base):
    """Celery task tracking"""
    __tablename__ = "jobs"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('ragdocuments.id', ondelete='CASCADE'),
        nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('tenants.id', ondelete='CASCADE'),
        nullable=False
    )
    step: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment='extract|normalize|split|embed.<MODEL>|commit|cleanup'
    )
    celery_task_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
        comment='Celery task UUID'
    )
    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default='pending',
        comment='pending|running|completed|failed|killed|canceled'
    )
    retries: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0')
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment='Error details with taxonomy'
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    __table_args__ = (
        Index('ix_jobs_document_id', 'document_id'),
        Index('ix_jobs_tenant_id', 'tenant_id'),
        Index('ix_jobs_celery_task_id', 'celery_task_id'),
        Index('ix_jobs_state', 'state'),
        Index('ix_jobs_step', 'step'),
        Index('ix_jobs_updated_at', 'updated_at'),
    )


class StatusHistory(Base):
    """Status transition history"""
    __tablename__ = "status_history"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('ragdocuments.id', ondelete='CASCADE'),
        nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('tenants.id', ondelete='CASCADE'),
        nullable=False
    )
    from_status: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment='Previous status'
    )
    to_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment='New status'
    )
    reason: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment='Reason for transition'
    )
    actor: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment='User/system who triggered transition'
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    
    __table_args__ = (
        Index('ix_status_history_document_id', 'document_id'),
        Index('ix_status_history_tenant_id', 'tenant_id'),
        Index('ix_status_history_created_at', 'created_at'),
        Index('ix_status_history_to_status', 'to_status'),
    )


class EventOutbox(Base):
    """Reliable event delivery via outbox pattern"""
    __tablename__ = "events_outbox"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seq: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        unique=True,
        comment='Sequential number for ordering (BIGSERIAL)'
    )
    type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment='rag.status|rag.embed.progress|rag.tags.updated|rag.deleted'
    )
    payload_json: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment='Event payload'
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment='Timestamp when event was delivered to at least one SSE client'
    )
    
    __table_args__ = (
        Index('ix_events_outbox_seq', 'seq'),
        Index('ix_events_outbox_type', 'type'),
        Index('ix_events_outbox_delivered_at', 'delivered_at'),
        Index('ix_events_outbox_created_at', 'created_at'),
    )


class ModelProgress(Base):
    """Embedding progress per model"""
    __tablename__ = "model_progress"
    
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('ragdocuments.id', ondelete='CASCADE'),
        nullable=False
    )
    model_alias: Mapped[str] = mapped_column(String(255), nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0')
    done: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0')
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    __table_args__ = (
        UniqueConstraint('document_id', 'model_alias', name='uq_model_progress_doc_model'),
        Index('ix_model_progress_document_id', 'document_id'),
        Index('ix_model_progress_model_alias', 'model_alias'),
    )

