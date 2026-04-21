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
  `user.stack.current`, `project.repo`, `department.standard_db`. It
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
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FactScope(str, Enum):
    """Where a fact is authoritative.

    * CHAT   — the fact matters only inside this chat
    * USER   — the fact is about this user across chats
    * TENANT — the fact is shared within a tenant (department)
    """
    CHAT = "chat"
    USER = "user"
    TENANT = "tenant"


class FactSource(str, Enum):
    """Where the fact originated from."""
    USER_UTTERANCE = "user_utterance"   # extracted from what the user said
    AGENT_RESULT = "agent_result"       # derived from an agent/tool result
    SYSTEM = "system"                   # system-provided (defaults, config)


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
        Index("ix_facts_user_scope", "user_id", "scope",
              postgresql_where="superseded_by IS NULL"),
        Index("ix_facts_chat_observed", "chat_id", "observed_at"),
        Index("ix_facts_tenant_scope", "tenant_id", "scope"),
        CheckConstraint(
            "scope IN ('chat', 'user', 'tenant')",
            name="ck_facts_scope",
        ),
        CheckConstraint(
            "source IN ('user_utterance', 'agent_result', 'system')",
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
    user_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    chat_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("chats.id", ondelete="CASCADE"),
        nullable=True,
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False)

    # --- payload ------------------------------------------------------------
    subject: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Canonical slot key, e.g. 'user.name', 'project.repo'.",
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
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

    # --- bookkeeping --------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


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
