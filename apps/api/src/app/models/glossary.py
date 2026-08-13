"""Canonical glossary entries used to resolve company terminology."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GlossaryScope(str, Enum):
    GLOBAL = "global"
    TENANT = "tenant"
    PROJECT = "project"


class GlossaryEntry(Base):
    """A canonical term, abbreviation, or entity alias.

    This is intentionally separate from facts: it answers "what entity does
    this spelling refer to?", not "what is true about that entity?".
    """

    __tablename__ = "glossary_entries"
    __table_args__ = (
        Index("uq_glossary_entries_scope_term", "scope", "tenant_id", "project_id", "canonical_term", unique=True),
        Index("ix_glossary_entries_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default=GlossaryScope.GLOBAL.value)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    canonical_term: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[List[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="term")
    entity_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
