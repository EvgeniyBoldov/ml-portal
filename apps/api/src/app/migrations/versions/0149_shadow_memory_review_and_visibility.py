"""Add tenant visibility, conflict review and audit to shadow document memory.

Revision ID: 0149
Revises: 0148
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0149"
down_revision = "0148"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB()
    op.add_column("document_memory_snapshots", sa.Column("visibility_tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True))
    op.add_column("memory_extraction_candidates", sa.Column("visibility_tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True))
    op.add_column("glossary_terms", sa.Column("visibility_tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True))
    op.create_index("ix_document_memory_snapshots_visibility_tenant_id", "document_memory_snapshots", ["visibility_tenant_id"])
    op.create_index("ix_memory_extraction_candidates_visibility_tenant_id", "memory_extraction_candidates", ["visibility_tenant_id"])
    op.create_index("ix_glossary_terms_visibility_tenant_id", "glossary_terms", ["visibility_tenant_id"])
    op.drop_constraint("uq_glossary_terms_normalized", "glossary_terms", type_="unique")
    op.create_index(
        "uq_glossary_terms_normalized_visibility", "glossary_terms",
        ["normalized_term", sa.text("COALESCE(visibility_tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)")], unique=True,
    )
    # Existing migration backfill is company knowledge, not a tenant upload.
    op.execute("UPDATE memory_extraction_candidates c SET visibility_tenant_id = s.visibility_tenant_id FROM document_memory_snapshots s WHERE c.snapshot_id = s.id")

    for table, constraint, condition in (
        ("document_memory_snapshots", "ck_document_memory_snapshot_state", "status IN ('queued', 'screening', 'studying', 'conflict_checking', 'awaiting_review', 'approved', 'rejected', 'skipped', 'failed', 'superseded', 'backfilled')"),
        ("memory_extraction_candidates", "ck_memory_candidate_resolution", "resolution_status IN ('extracted', 'conflict', 'needs_review', 'resolved', 'rejected', 'stale')"),
        ("glossary_meanings", "ck_glossary_meaning_resolution", "resolution_status IN ('extracted', 'conflict', 'needs_review', 'resolved', 'rejected', 'stale')"),
    ):
        op.drop_constraint(constraint, table, type_="check")
        op.create_check_constraint(constraint, table, condition)
    op.execute("UPDATE document_memory_snapshots SET status = 'awaiting_review' WHERE status = 'ready_for_review'")

    op.create_table(
        "memory_conflict_cases",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("visibility_tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("rationale", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("resolved_by_user_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("kind IN ('duplicate', 'compatible_extension', 'scope_override', 'contradiction', 'insufficient_evidence')", name="ck_memory_conflict_kind"),
        sa.CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name="ck_memory_conflict_status"),
    )
    op.create_index("ix_memory_conflicts_visibility_status", "memory_conflict_cases", ["visibility_tenant_id", "status"])
    op.create_table(
        "memory_conflict_members",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("conflict_id", uuid, sa.ForeignKey("memory_conflict_cases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", uuid, sa.ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False, server_default="candidate"),
        sa.UniqueConstraint("conflict_id", "candidate_id", name="uq_memory_conflict_member"),
    )
    op.create_index("ix_memory_conflict_members_conflict_id", "memory_conflict_members", ["conflict_id"])
    op.create_index("ix_memory_conflict_members_candidate_id", "memory_conflict_members", ["candidate_id"])
    op.create_table(
        "memory_candidate_decisions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("candidate_id", uuid, sa.ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", uuid, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_memory_candidate_decisions_candidate", "memory_candidate_decisions", ["candidate_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_memory_candidate_decisions_candidate", table_name="memory_candidate_decisions")
    op.drop_table("memory_candidate_decisions")
    op.drop_index("ix_memory_conflict_members_candidate_id", table_name="memory_conflict_members")
    op.drop_index("ix_memory_conflict_members_conflict_id", table_name="memory_conflict_members")
    op.drop_table("memory_conflict_members")
    op.drop_index("ix_memory_conflicts_visibility_status", table_name="memory_conflict_cases")
    op.drop_table("memory_conflict_cases")
    op.drop_index("uq_glossary_terms_normalized_visibility", table_name="glossary_terms")
    op.create_unique_constraint("uq_glossary_terms_normalized", "glossary_terms", ["normalized_term"])
    for index, table in (("ix_glossary_terms_visibility_tenant_id", "glossary_terms"), ("ix_memory_extraction_candidates_visibility_tenant_id", "memory_extraction_candidates"), ("ix_document_memory_snapshots_visibility_tenant_id", "document_memory_snapshots")):
        op.drop_index(index, table_name=table)
    op.drop_column("glossary_terms", "visibility_tenant_id")
    op.drop_column("memory_extraction_candidates", "visibility_tenant_id")
    op.drop_column("document_memory_snapshots", "visibility_tenant_id")
