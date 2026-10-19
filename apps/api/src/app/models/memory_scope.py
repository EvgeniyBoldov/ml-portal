"""Typed applicability contexts for document-derived knowledge."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins.lifecycle import LifecycleMixin


class MemoryScopeType(str, Enum):
    PROJECT = "project"


class MemoryScope(Base, LifecycleMixin):
    __tablename__ = "memory_scopes"
    __table_args__ = (
        UniqueConstraint("key", name="uq_memory_scopes_key"),
        UniqueConstraint("project_id", name="uq_memory_scopes_project_id"),
        CheckConstraint("key ~ '^[a-z0-9][a-z0-9._-]*$'", name="ck_memory_scopes_slug"),
        CheckConstraint("scope_type = 'project' AND NOT is_all", name="ck_memory_scopes_flat"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type: Mapped[str] = mapped_column(ENUM(
        "project", "team", name="memoryscopetype", create_type=False,
    ), nullable=False, default="project", server_default="project")
    project_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    key: Mapped[str] = mapped_column(String(180), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    is_all: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class MemoryScopeGlossaryTerm(Base):
    """A glossary term that names a typed applicability scope."""
    __tablename__ = "memory_scope_glossary_terms"

    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_scopes.id", ondelete="CASCADE"), primary_key=True)
    glossary_term_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("glossary_terms.id", ondelete="CASCADE"), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class DocumentMemoryScope(Base):
    """Document applicability for the native scope corpus; independent of source access."""
    __tablename__ = "document_memory_scopes"

    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ragdocuments.id", ondelete="CASCADE"), primary_key=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_scopes.id", ondelete="RESTRICT"), primary_key=True)
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="explicit")


class MemoryCandidateScope(Base):
    """Proposed applicability or mere mention, pending review."""
    __tablename__ = "memory_candidate_scopes"
    __table_args__ = (
        UniqueConstraint("candidate_id", "scope_id", "role", name="uq_memory_candidate_scopes_binding"),
        CheckConstraint("role IN ('applies_to', 'mentions')", name="ck_memory_candidate_scopes_role"),
        CheckConstraint("status IN ('suggested', 'confirmed', 'rejected')", name="ck_memory_candidate_scopes_status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_candidate_scopes_confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_scopes.id", ondelete="RESTRICT"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="suggested", server_default="suggested")
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)


class MemoryClaimScope(Base):
    """Published applicability, attached to a source claim."""
    __tablename__ = "memory_claim_scopes"

    claim_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_claims.id", ondelete="CASCADE"), primary_key=True)
    scope_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_scopes.id", ondelete="RESTRICT"), primary_key=True)
