"""Typed applicability contexts for document-derived knowledge."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MemoryScopeType(str, Enum):
    PRODUCT = "product"
    PROJECT = "project"
    TEAM = "team"


class MemoryScope(Base):
    __tablename__ = "memory_scopes"
    __table_args__ = (
        UniqueConstraint("scope_type", "key", name="uq_memory_scopes_type_key"),
        Index("uq_memory_scopes_all_type", "scope_type", unique=True, postgresql_where="is_all"),
        UniqueConstraint("project_id", name="uq_memory_scopes_project_id"),
        CheckConstraint("key LIKE scope_type::text || '.%' AND ((is_all AND key = scope_type::text || '.all') OR (NOT is_all AND key <> scope_type::text || '.all'))", name="ck_memory_scopes_all_key"),
        CheckConstraint("project_id IS NULL OR (scope_type = 'project' AND NOT is_all)", name="ck_memory_scopes_project_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope_type: Mapped[str] = mapped_column(ENUM(
        "product", "project", "team", name="memoryscopetype", create_type=False,
    ), nullable=False)
    key: Mapped[str] = mapped_column(String(180), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    is_all: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class DocumentMemoryScope(Base):
    """A document-level hint; it never grants access or scopes every claim."""
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
