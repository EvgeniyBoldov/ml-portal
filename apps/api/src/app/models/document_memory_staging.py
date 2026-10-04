"""Canonical staging model for document-derived semantic knowledge.

The existing ``MemoryItem`` / ``MemoryClaim`` pair remains the published
compatibility projection until runtime recall moves to this model.  These
tables deliberately retain an extraction before forcing it into a single
company-or-project identity.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocumentMemorySnapshot(Base):
    """An immutable extraction attempt over one canonical document revision."""

    __tablename__ = "document_memory_snapshots"
    __table_args__ = (
        UniqueConstraint("document_id", "canonical_checksum", name="uq_document_memory_snapshot_revision"),
        Index("ix_document_memory_snapshots_document", "document_id", "created_at"),
        CheckConstraint("status IN ('queued', 'screening', 'studying', 'conflict_checking', 'awaiting_review', 'approved', 'rejected', 'skipped', 'failed', 'superseded', 'backfilled')", name="ck_document_memory_snapshot_state"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=False)
    # NULL is company-visible.  A tenant upload is private until an admin
    # explicitly promotes its approved result.
    visibility_tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    canonical_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    extractor_version: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # A shadow study spans several Celery tasks. This durable relation is the
    # sole correlation key for its runtime journal; task names and timestamps
    # are never used to reconstruct the trace.
    trace_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    active_attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("document_memory_extraction_attempts.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", server_default="queued")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class DocumentMemoryExtractionAttempt(Base):
    """One immutable, retryable study pass for a document snapshot."""
    __tablename__ = "document_memory_extraction_attempts"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "attempt_number", name="uq_document_memory_attempt_number"),
        CheckConstraint("status IN ('queued', 'studying', 'awaiting_review', 'completed', 'failed', 'superseded')", name="ck_document_memory_attempt_status"),
        CheckConstraint("attempt_number > 0", name="ck_document_memory_attempt_number"),
        Index("ix_document_memory_attempts_status", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_memory_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", server_default="queued")
    next_section: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    feedback: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    trace_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MemoryExtractionCandidate(Base):
    """A source-backed statement before scope resolution and publication."""

    __tablename__ = "memory_extraction_candidates"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "ordinal", name="uq_memory_candidate_snapshot_ordinal"),
        UniqueConstraint("legacy_memory_claim_id", name="uq_memory_candidate_legacy_claim"),
        Index("ix_memory_candidates_resolution", "resolution_status", "scope_candidate"),
        Index("ix_memory_candidates_subject", "candidate_type", "normalized_subject"),
        CheckConstraint("candidate_type IN ('term', 'description', 'relationship', 'rule', 'constraint', 'procedure', 'decision')", name="ck_memory_candidate_type"),
        CheckConstraint("scope_candidate IS NULL OR scope_candidate IN ('global', 'project', 'multi_project', 'scoped', 'unknown')", name="ck_memory_candidate_scope"),
        CheckConstraint("resolution_status IN ('extracted', 'conflict', 'needs_review', 'resolved', 'rejected', 'stale')", name="ck_memory_candidate_resolution"),
        CheckConstraint("resolution_method IS NULL OR resolution_method IN ('document_hint', 'exact_project_key', 'unique_alias', 'content_evidence', 'llm_suggestion', 'manual', 'migration')", name="ck_memory_candidate_resolution_method"),
        CheckConstraint("extraction_confidence >= 0.0 AND extraction_confidence <= 1.0", name="ck_memory_candidate_confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_memory_snapshots.id", ondelete="CASCADE"), nullable=False)
    visibility_tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    # These links make the P0 backfill auditable; they are not a dependency of
    # the future write path and therefore are nullable.
    legacy_memory_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_items.id", ondelete="SET NULL"), nullable=True)
    legacy_memory_claim_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_claims.id", ondelete="SET NULL"), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("document_memory_extraction_attempts.id", ondelete="CASCADE"), nullable=True, index=True)
    candidate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_subject: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_section_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    related_entities: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    related_project_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    unmatched_scope_names: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    unresolved_scope_references: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    scope_candidate: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(16), nullable=False, default="extracted", server_default="extracted")
    resolution_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    resolution_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MemoryCandidateProjectBinding(Base):
    """A project applicability or mention edge for one extracted candidate."""

    __tablename__ = "memory_candidate_project_bindings"
    __table_args__ = (
        UniqueConstraint("candidate_id", "project_id", "role", name="uq_memory_candidate_project_binding"),
        Index("ix_memory_candidate_project_binding_project", "project_id", "status"),
        CheckConstraint("role IN ('applies_to', 'mentions')", name="ck_memory_candidate_project_binding_role"),
        CheckConstraint("status IN ('suggested', 'confirmed', 'rejected')", name="ck_memory_candidate_project_binding_status"),
        CheckConstraint("method IN ('document_hint', 'exact_project_key', 'unique_alias', 'content_evidence', 'llm_suggestion', 'manual', 'migration')", name="ck_memory_candidate_project_binding_method"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_memory_candidate_project_binding_confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="suggested", server_default="suggested")
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class GlossaryTerm(Base):
    """An administrator-approved lexical identity without applicability scopes."""

    __tablename__ = "glossary_terms"
    __table_args__ = (
        UniqueConstraint("normalized_term", name="uq_glossary_terms_normalized"),
        CheckConstraint("NOT is_active OR (definition IS NOT NULL AND btrim(definition) <> '')", name="ck_glossary_active_definition"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_term: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    approved_candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("memory_extraction_candidates.id", ondelete="SET NULL", name="fk_glossary_terms_approved_candidate"), nullable=True, index=True,
    )
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MemoryScopeProposal(Base):
    """A typed scope awaiting approval, grounded in document evidence, optionally linked to a glossary term."""
    __tablename__ = "memory_scope_proposals"
    __table_args__ = (
        CheckConstraint("scope_type IN ('project', 'team')", name="ck_memory_scope_proposal_type"),
        CheckConstraint("status IN ('awaiting_term', 'needs_review', 'approved', 'rejected', 'superseded')", name="ck_memory_scope_proposal_status"),
        CheckConstraint("term_candidate_id IS NULL OR glossary_term_id IS NULL", name="ck_memory_scope_proposal_term_source"),
        Index("ix_memory_scope_proposals_status", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_memory_snapshots.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("document_memory_extraction_attempts.id", ondelete="CASCADE"), nullable=True, index=True)
    visibility_tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    project_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    proposed_key: Mapped[str] = mapped_column(String(180), nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(180), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="'[]'::jsonb")
    term_candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=True, index=True)
    source_term_candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_extraction_candidates.id", ondelete="SET NULL"), nullable=True, index=True)
    glossary_term_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("glossary_terms.id", ondelete="CASCADE"), nullable=True, index=True)
    memory_scope_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_scopes.id", ondelete="RESTRICT"), nullable=True, index=True)
    evidence_section_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="awaiting_term", server_default="awaiting_term")
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    review_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MemoryCandidateScopeProposal(Base):
    """An applies-to or mention edge to a scope proposal."""
    __tablename__ = "memory_candidate_scope_proposals"
    __table_args__ = (
        UniqueConstraint("candidate_id", "scope_proposal_id", "role", name="uq_memory_candidate_scope_proposal_binding"),
        CheckConstraint("role IN ('applies_to', 'mentions')", name="ck_memory_candidate_scope_proposal_role"),
        CheckConstraint("status IN ('suggested', 'confirmed', 'rejected', 'superseded')", name="ck_memory_candidate_scope_proposal_status"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_candidate_scope_proposal_confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    scope_proposal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_scope_proposals.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="suggested", server_default="suggested")
    method: Mapped[str] = mapped_column(String(32), nullable=False, default="llm_suggestion", server_default="llm_suggestion")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)



class MemoryConflictCase(Base):
    """A reviewable incompatibility or deterministic duplicate finding."""

    __tablename__ = "memory_conflict_cases"
    __table_args__ = (
        Index("ix_memory_conflicts_visibility_status", "visibility_tenant_id", "status"),
        CheckConstraint("kind IN ('duplicate', 'compatible_extension', 'scope_override', 'contradiction', 'insufficient_evidence')", name="ck_memory_conflict_kind"),
        CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name="ck_memory_conflict_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visibility_tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open", server_default="open")
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    resolved_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MemoryConflictMember(Base):
    __tablename__ = "memory_conflict_members"
    __table_args__ = (UniqueConstraint("conflict_id", "candidate_id", name="uq_memory_conflict_member"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conflict_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_conflict_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="candidate", server_default="candidate")


class MemoryCandidateDecision(Base):
    """Append-only approval/rejection/audit record for staged knowledge."""

    __tablename__ = "memory_candidate_decisions"
    __table_args__ = (Index("ix_memory_candidate_decisions_candidate", "candidate_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=False)
    actor_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(24), nullable=False)  # approve|reject|autoapprove|edit|resolve_conflict
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
