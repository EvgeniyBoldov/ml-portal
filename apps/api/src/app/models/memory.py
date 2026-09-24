"""Runtime memory models: typed Facts and structured DialogueSummary.

Purpose
-------
These two tables replace the legacy JSONB-blob memory layer
(`runs.memory_state` + ad-hoc string summaries). They form the
persistence side of the new memory architecture:

    Turn start:  MemoryBuilder.build()  reads from both tables
                                        (plus optional resume state)
    Turn end:    MemoryWriter.finalize() upserts into both tables
                                        via FactStore / SummaryStore

Design notes
------------
* `Fact` is atomic and immutable-on-update: on contradiction we mark
  the old row with `superseded_by = new_id` rather than mutating
  `value`. Retrieval filters `superseded_by IS NULL`. This gives us
  free audit trail and a clean "forget" primitive (soft-delete by
  setting `superseded_by`).
* `subject` is a canonical slot key: e.g. `user.name`,
  `user.stack.current`, `department.standard_db`. It
  is what callers query on, so it is **indexed** — both alone and in
  composite with `scope`.
* `DialogueSummary` is **per-chat**, `chat_id` is the primary key. We
  deliberately chose structured JSONB fields over a monolithic blob so
  the planner / synthesizer can read specific facets (goals,
  open_questions) without re-parsing a string.
* We do NOT engineer row-level tenant isolation here. The product is
  internal; `tenant_id` is kept as an indexed filter, not a security
  boundary.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.mixins.lifecycle import LifecycleMixin


class FactScope(str, Enum):
    """Where a fact is authoritative.

    * USER   — the fact is about this user across chats
    * TENANT — the fact is shared within a tenant (department)
    """
    USER = "user"
    TENANT = "tenant"


class FactStatus(str, Enum):
    """Whether a fact may be injected into planning context."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"
    DELETED = "deleted"


class FactSource(str, Enum):
    """Where the fact originated from."""
    USER_UTTERANCE = "user_utterance"   # extracted from what the user said
    TOOL_RESULT = "tool_result"         # direct successful tool result
    MANUAL = "manual"                   # explicitly edited by the user
    SYSTEM = "system"                   # system-provided (defaults, config)
    LEGACY_AGENT_RESULT = "agent_result" # read-only compatibility; never emitted


class Fact(Base):
    """A single atomic piece of knowledge used by the runtime.

    Facts are written at turn end by `MemoryWriter.finalize` and read
    at turn start by `MemoryBuilder.build`. See module docstring for
    the contradiction model (soft supersede via `superseded_by`).
    """
    __tablename__ = "facts"
    __table_args__ = (
        # Active-row lookup by subject within a scope is the hot path
        # (`"what is user.name for user X?"`). Keep it cheap.
        Index("ix_facts_scope_subject_active", "scope", "subject",
              postgresql_where="superseded_by IS NULL"),
        Index("ix_facts_tenant_scope", "tenant_id", "scope"),
        Index("ix_facts_owner_subject_active", "owner_type", "owner_id", "subject",
              postgresql_where="superseded_by IS NULL"),
        CheckConstraint("scope IN ('user', 'tenant')", name="ck_facts_scope"),
        CheckConstraint(
            "source IN ('user_utterance', 'tool_result', 'manual', 'system', 'agent_result')",
            name="ck_facts_source",
        ),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_facts_confidence_range",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # --- ownership / scoping ------------------------------------------------
    # All three are nullable because scope decides which ones must be set:
    # CHAT   → chat_id required, user_id+tenant_id optional context
    # USER   → user_id required, tenant_id optional context
    # TENANT → tenant_id required
    tenant_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    # Generic ownership is the canonical contract for new rows. Legacy
    # user_id/tenant_id/chat_id remain during the compatibility transition.
    owner_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    owner_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    kind: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entry_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column("metadata", JSONB, nullable=True)

    # --- payload ------------------------------------------------------------
    subject: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Canonical slot key, e.g. 'user.name', 'department.standard_db'.",
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_value: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )

    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="message_id / run_id / tool_call_id — for audit and delete.",
    )

    # --- lifecycle ----------------------------------------------------------
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    superseded_by: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="If set, this fact is no longer active; id of the replacing row.",
    )

    # --- future: user-facing fact editing -----------------------------------
    user_visible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether the user may list / delete this fact via user API.",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=FactStatus.PENDING.value,
        server_default=FactStatus.PENDING.value,
    )
    support_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    first_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    # --- bookkeeping --------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class FactObservation(Base):
    """A unique source event which supports one fact.

    Observations are intentionally small: the source reference lets callers
    re-authorize evidence later without storing a second copy of RAG content.
    """

    __tablename__ = "fact_observations"
    __table_args__ = (
        Index("uq_fact_observations_fact_source", "fact_id", "source_type", "source_ref", unique=True),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fact_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("facts.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    source_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class MemoryItem(Base, LifecycleMixin):
    """Typed, document-derived semantic memory.

    Unlike legacy ``Fact``, a MemoryItem may carry a complete procedure or
    rule in ``content``.  It is intentionally source-backed and never becomes
    active without at least one MemoryItemSource row.
    """

    __tablename__ = "memory_items"
    __table_args__ = (
        Index(
            "uq_memory_items_identity", "scope", "item_type",
            text("COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "normalized_subject", "scope_signature", unique=True,
        ),
        Index("ix_memory_items_project_active", "project_id", "state"),
        Index("ix_memory_items_scope_subject", "scope", "subject"),
        CheckConstraint("scope IN ('company', 'project')", name="ck_memory_items_scope"),
        CheckConstraint("state IN ('active', 'stale', 'uncertain')", name="ck_memory_items_state"),
        CheckConstraint(
            "item_type IN ('description', 'relationship', 'rule', 'constraint', 'procedure', 'decision')",
            name="ck_memory_items_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    scope_signature: Mapped[str] = mapped_column(String(80), nullable=False, default="legacy", server_default="legacy")
    owner_type: Mapped[str] = mapped_column(String(32), nullable=False, default="company", server_default="company")
    owner_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    applicability: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))
    visibility: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{\"mode\": \"source\"}'::jsonb"))
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_subject: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1")
    project_resolution_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    source_trust: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    last_verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MemoryItemSource(Base):
    """A bounded provenance binding from semantic memory to a canonical document section."""

    __tablename__ = "memory_item_sources"
    __table_args__ = (
        Index(
            "uq_memory_item_sources_binding",
            "memory_item_id", "document_id", "canonical_checksum", "section_id", unique=True,
        ),
        Index("ix_memory_item_sources_document", "document_id", "canonical_checksum"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    document_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    canonical_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    section_id: Mapped[str] = mapped_column(String(128), nullable=False)
    start_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    end_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    excerpt_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class MemoryClaim(Base, LifecycleMixin):
    """One source-backed extraction claim, prior to semantic consolidation."""

    __tablename__ = "memory_claims"
    __table_args__ = (
        Index(
            "uq_memory_claim_source_identity", "document_id", "canonical_checksum", "scope", "item_type",
            text("COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            "normalized_subject", "scope_signature", unique=True,
        ),
        Index("ix_memory_claims_item_state", "memory_item_id", "state"),
        CheckConstraint("scope IN ('company', 'project')", name="ck_memory_claims_scope"),
        CheckConstraint("state IN ('active', 'stale', 'conflict')", name="ck_memory_claims_state"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=False, index=True)
    canonical_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    project_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    scope_signature: Mapped[str] = mapped_column(String(80), nullable=False, default="legacy", server_default="legacy")
    # NULL means company-visible source; a value means evidence available
    # only through that tenant's local document scope.
    visibility_tenant_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    applicability: Mapped[Dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"),
    )
    normalized_subject: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_section_ids: Mapped[List[str]] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    extraction_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1")
    project_resolution_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    source_trust: Mapped[float] = mapped_column(Float, nullable=False, default=1.0, server_default="1")
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MemoryRelation(Base):
    """Typed edge from a semantic item to a company entity."""

    __tablename__ = "memory_relations"
    __table_args__ = (
        Index("uq_memory_relations_edge", "memory_item_id", "document_id", "relation_type", "target_type", "target_id", unique=True),
        Index("ix_memory_relations_target", "target_type", "target_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class MemoryItemEvaluation(Base):
    """Evidence-only trust decision for one semantic memory item."""

    __tablename__ = "memory_item_evaluations"
    __table_args__ = (
        Index("uq_memory_item_evaluations_item_call", "memory_item_id", "tool_call_id", unique=True),
        Index("ix_memory_item_evaluations_item_created", "memory_item_id", "created_at"),
        CheckConstraint(
            "outcome IN ('confirmed', 'contradicted', 'insufficient', 'irrelevant')",
            name="ck_memory_item_evaluations_outcome",
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    tool_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_refs: Mapped[List[Dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class DialogueSummary(Base):
    """Structured per-chat summary. One row per chat (chat_id is PK).

    Replaces the legacy monolithic `summary_text` string. Fields are
    JSONB arrays / maps so that the planner can read `open_questions`
    without having to parse prose.

    `raw_tail` stays as text — it is a fallback for small-context local
    models, literally the last N messages verbatim (capped by character
    budget, not message count).
    """
    __tablename__ = "dialogue_summaries"
    __table_args__ = (
        Index("ix_dialogue_summaries_updated", "updated_at"),
    )

    chat_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # --- structured facets --------------------------------------------------
    goals: Mapped[List[str]] = mapped_column(
        JSONB, nullable=False, default=list,
        comment="Open user objectives for this chat.",
    )
    done: Mapped[List[str]] = mapped_column(
        JSONB, nullable=False, default=list,
        comment="What has already been accomplished in this chat.",
    )
    entities: Mapped[Dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=dict,
        comment="Key entities referenced (files, projects, agents used).",
    )
    open_questions: Mapped[List[str]] = mapped_column(
        JSONB, nullable=False, default=list,
        comment="Things the user asked that have not been fully answered yet.",
    )

    # --- raw fallback -------------------------------------------------------
    raw_tail: Mapped[str] = mapped_column(
        Text, nullable=False, default="",
        comment="Last N exchanges verbatim, capped by character budget.",
    )
    summary_v2: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        server_default=text("'{}'::jsonb"),
        comment="Structured summary v2 payload (dual-write/read-fallback migration path).",
    )

    # --- bookkeeping --------------------------------------------------------
    last_updated_turn: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
