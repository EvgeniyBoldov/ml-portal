"""Canonical company entities used by semantic-memory relations."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeEntity(Base):
    __tablename__ = "knowledge_entities"
    __table_args__ = (
        UniqueConstraint("entity_type", "normalized_name", name="uq_knowledge_entities_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class KnowledgeEntitySource(Base):
    """Tenant-visible document evidence for an entity, aliases and project link."""

    __tablename__ = "knowledge_entity_sources"
    __table_args__ = (
        # PostgreSQL considers NULL values distinct in a regular unique
        # constraint. Company-level bindings have project_id=NULL, so their
        # identity needs the same sentinel strategy as MemoryClaim.
        Index(
            "uq_knowledge_entity_sources_document",
            "entity_id", "document_id", "canonical_checksum",
            text("COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
            unique=True,
        ),
        Index("ix_knowledge_entity_sources_document", "document_id"),
        Index("ix_knowledge_entity_sources_project", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=False)
    canonical_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    visibility_tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    evidence_section_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
