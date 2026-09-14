"""Track document evidence for knowledge-entity aliases.

Revision ID: 0132
Revises: 0131
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0132"
down_revision = "0131"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_entity_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("knowledge_entities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_checksum", sa.String(length=128), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("entity_id", "document_id", "canonical_checksum", name="uq_knowledge_entity_sources_document"),
    )
    op.create_index("ix_knowledge_entity_sources_document", "knowledge_entity_sources", ["document_id"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_entity_sources_document", table_name="knowledge_entity_sources")
    op.drop_table("knowledge_entity_sources")
