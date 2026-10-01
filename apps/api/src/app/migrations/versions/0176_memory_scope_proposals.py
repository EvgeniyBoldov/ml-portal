"""Add staged typed memory scope proposals and candidate bindings.

Revision ID: 0176
Revises: 0175
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0176"
down_revision = "0175"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_scope_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_memory_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visibility_tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE")),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("proposed_key", sa.String(180), nullable=False),
        sa.Column("normalized_key", sa.String(180), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("aliases", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("term_candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE")),
        sa.Column("glossary_term_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("glossary_terms.id", ondelete="CASCADE")),
        sa.Column("memory_scope_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("memory_scopes.id", ondelete="RESTRICT"), unique=True),
        sa.Column("evidence_section_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="awaiting_term"),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("review_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("scope_type IN ('product', 'project', 'team')", name="ck_memory_scope_proposal_type"),
        sa.CheckConstraint("status IN ('awaiting_term', 'needs_review', 'approved', 'rejected')", name="ck_memory_scope_proposal_status"),
        sa.CheckConstraint("(term_candidate_id IS NULL) <> (glossary_term_id IS NULL)", name="ck_memory_scope_proposal_term_source"),
    )
    op.create_index("ix_memory_scope_proposals_snapshot_id", "memory_scope_proposals", ["snapshot_id"])
    op.create_index("ix_memory_scope_proposals_visibility_tenant_id", "memory_scope_proposals", ["visibility_tenant_id"])
    op.create_index("ix_memory_scope_proposals_term_candidate_id", "memory_scope_proposals", ["term_candidate_id"])
    op.create_index("ix_memory_scope_proposals_glossary_term_id", "memory_scope_proposals", ["glossary_term_id"])
    op.create_index("ix_memory_scope_proposals_status", "memory_scope_proposals", ["status", "created_at"])
    op.create_index("ix_memory_scope_proposals_identity", "memory_scope_proposals", ["scope_type", "normalized_key"])
    op.create_table(
        "memory_candidate_scope_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_proposal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("memory_scope_proposals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="suggested"),
        sa.Column("method", sa.String(32), nullable=False, server_default="llm_suggestion"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.Text()),
        sa.UniqueConstraint("candidate_id", "scope_proposal_id", "role", name="uq_memory_candidate_scope_proposal_binding"),
        sa.CheckConstraint("role IN ('applies_to', 'mentions')", name="ck_memory_candidate_scope_proposal_role"),
        sa.CheckConstraint("status IN ('suggested', 'confirmed', 'rejected')", name="ck_memory_candidate_scope_proposal_status"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_candidate_scope_proposal_confidence"),
    )
    op.create_index("ix_memory_candidate_scope_proposals_candidate_id", "memory_candidate_scope_proposals", ["candidate_id"])
    op.create_index("ix_memory_candidate_scope_proposals_scope_proposal_id", "memory_candidate_scope_proposals", ["scope_proposal_id"])
    op.create_table(
        "memory_scope_glossary_terms",
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("memory_scopes.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("glossary_term_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("glossary_terms.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("memory_scope_glossary_terms")
    op.drop_table("memory_candidate_scope_proposals")
    op.drop_table("memory_scope_proposals")
