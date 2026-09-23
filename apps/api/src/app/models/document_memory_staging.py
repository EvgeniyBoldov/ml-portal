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
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", server_default="queued")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
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
    candidate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_subject: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_section_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    related_entities: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    related_project_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
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
    """A scope-free canonical spelling and its aliases, without a definition."""

    __tablename__ = "glossary_terms"
    __table_args__ = (UniqueConstraint("normalized_term", name="uq_glossary_terms_normalized"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_term: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class GlossaryMeaning(Base):
    """Historical scoped definition; new definitions are memory candidates."""

    __tablename__ = "glossary_meanings"
    __table_args__ = (
        UniqueConstraint("legacy_glossary_entry_id", name="uq_glossary_meaning_legacy_entry"),
        Index("ix_glossary_meanings_term_resolution", "term_id", "resolution_status"),
        CheckConstraint("scope_candidate IN ('global', 'project', 'multi_project', 'unknown')", name="ck_glossary_meaning_scope"),
        CheckConstraint("resolution_status IN ('extracted', 'conflict', 'needs_review', 'resolved', 'rejected', 'stale')", name="ck_glossary_meaning_resolution"),
        CheckConstraint("resolution_method IS NULL OR resolution_method IN ('document_hint', 'exact_project_key', 'unique_alias', 'content_evidence', 'llm_suggestion', 'manual', 'migration')", name="ck_glossary_meaning_resolution_method"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_glossary_meaning_confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    term_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("glossary_terms.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_extraction_candidates.id", ondelete="SET NULL"), nullable=True)
    legacy_glossary_entry_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("glossary_entries.id", ondelete="SET NULL"), nullable=True)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    scope_candidate: Mapped[str] = mapped_column(String(16), nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(16), nullable=False, default="extracted", server_default="extracted")
    resolution_method: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    resolution_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    visibility_tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class GlossaryMeaningProjectBinding(Base):
    """Confirmed or proposed project applicability for one glossary meaning."""

    __tablename__ = "glossary_meaning_project_bindings"
    __table_args__ = (
        UniqueConstraint("meaning_id", "project_id", name="uq_glossary_meaning_project_binding"),
        Index("ix_glossary_meaning_project_binding_project", "project_id", "status"),
        CheckConstraint("status IN ('suggested', 'confirmed', 'rejected')", name="ck_glossary_meaning_project_binding_status"),
        CheckConstraint("method IN ('document_hint', 'exact_project_key', 'unique_alias', 'content_evidence', 'llm_suggestion', 'manual', 'migration')", name="ck_glossary_meaning_project_binding_method"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_glossary_meaning_project_binding_confidence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meaning_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("glossary_meanings.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="suggested", server_default="suggested")
    method: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class GlossaryMeaningSource(Base):
    """Evidence binding for a glossary meaning from a candidate or legacy observation."""

    __tablename__ = "glossary_meaning_sources"
    __table_args__ = (
        UniqueConstraint("meaning_id", "legacy_glossary_observation_id", name="uq_glossary_meaning_source_legacy_observation"),
        UniqueConstraint("meaning_id", "candidate_id", name="uq_glossary_meaning_source_candidate"),
        Index("ix_glossary_meaning_sources_document", "document_id"),
        CheckConstraint("(candidate_id IS NOT NULL)::integer + (legacy_glossary_observation_id IS NOT NULL)::integer = 1", name="ck_glossary_meaning_source_origin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meaning_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("glossary_meanings.id", ondelete="CASCADE"), nullable=False)
    candidate_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=True)
    legacy_glossary_observation_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("glossary_observations.id", ondelete="SET NULL"), nullable=True)
    document_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=True)
    visibility_tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    evidence_section_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


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
