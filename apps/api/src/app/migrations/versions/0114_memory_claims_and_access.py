"""Add claim-based consolidation and semantic-memory access metadata.

Revision ID: 0114
Revises: 0113
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0114"
down_revision = "0113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memory_items", sa.Column("owner_type", sa.String(length=32), nullable=False, server_default="company"))
    op.add_column("memory_items", sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("memory_items", sa.Column("applicability", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("memory_items", sa.Column("visibility", postgresql.JSONB(), nullable=False, server_default=sa.text("'{\"mode\": \"source\"}'::jsonb")))
    op.execute(sa.text("UPDATE memory_items SET owner_type = CASE WHEN scope = 'project' THEN 'project' ELSE 'company' END, owner_id = project_id WHERE scope = 'project'"))

    op.create_table(
        "memory_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("memory_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_checksum", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("normalized_subject", sa.String(length=200), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("evidence_section_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("scope IN ('company', 'project')", name="ck_memory_claims_scope"),
        sa.CheckConstraint("state IN ('active', 'stale', 'conflict')", name="ck_memory_claims_state"),
    )
    op.create_index("uq_memory_claim_source_identity", "memory_claims", ["document_id", "canonical_checksum", "scope", "item_type", "project_id", "normalized_subject"], unique=True)
    op.create_index("ix_memory_claims_item_state", "memory_claims", ["memory_item_id", "state"])

    op.create_table(
        "memory_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("memory_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("uq_memory_relations_edge", "memory_relations", ["memory_item_id", "relation_type", "target_type", "target_id"], unique=True)
    op.create_index("ix_memory_relations_target", "memory_relations", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_table("memory_relations")
    op.drop_table("memory_claims")
    op.drop_column("memory_items", "visibility")
    op.drop_column("memory_items", "applicability")
    op.drop_column("memory_items", "owner_id")
    op.drop_column("memory_items", "owner_type")
