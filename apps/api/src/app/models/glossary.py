"""Canonical glossary entries used to resolve company terminology."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GlossaryScope(str, Enum):
    GLOBAL = "global"
    USER = "user"
    TENANT = "tenant"
    PROJECT = "project"


class GlossaryStatus(str, Enum):
    """Whether a glossary entry is ready for user and runtime reads."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"


class GlossaryEntry(Base):
    """A canonical term, abbreviation, or entity alias.

    This is intentionally separate from facts: it answers "what entity does
    this spelling refer to?", not "what is true about that entity?".
    """

    __tablename__ = "glossary_entries"
    __table_args__ = (
        Index("uq_glossary_entries_scope_term", "scope", "tenant_id", "project_id", "canonical_term", unique=True),
        Index("ix_glossary_entries_entity", "entity_type", "entity_id"),
        CheckConstraint(
            "scope IN ('global', 'user', 'tenant', 'project')",
            name="ck_glossary_entries_scope",
        ),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'unconfirmed')",
            name="ck_glossary_entries_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default=GlossaryScope.GLOBAL.value)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    canonical_term: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="term")
    entity_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=GlossaryStatus.CONFIRMED.value,
        server_default=GlossaryStatus.CONFIRMED.value,
    )
    support_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3",
    )
    first_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class GlossaryObservation(Base):
    """A distinct evidence source supporting an automatically extracted term."""

    __tablename__ = "glossary_observations"
    __table_args__ = (
        Index(
            "uq_glossary_observations_entry_source",
            "entry_id", "source_type", "source_ref", unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("glossary_entries.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    source_label: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
