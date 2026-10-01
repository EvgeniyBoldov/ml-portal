"""Add repeatable extraction attempts and stable term/scope proposal links.

Revision ID: 0177
Revises: 0176
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0177"
down_revision = "0176"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_memory_extraction_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("document_memory_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("next_section", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("feedback", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("trace_run_id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("snapshot_id", "attempt_number", name="uq_document_memory_attempt_number"),
        sa.CheckConstraint("status IN ('queued', 'studying', 'awaiting_review', 'completed', 'failed', 'superseded')", name="ck_document_memory_attempt_status"),
        sa.CheckConstraint("attempt_number > 0", name="ck_document_memory_attempt_number"),
    )
    op.create_index("ix_document_memory_extraction_attempts_snapshot_id", "document_memory_extraction_attempts", ["snapshot_id"])
    op.create_index("ix_document_memory_attempts_status", "document_memory_extraction_attempts", ["status", "updated_at"])

    op.add_column("document_memory_snapshots", sa.Column("active_attempt_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_document_memory_snapshots_active_attempt", "document_memory_snapshots", "document_memory_extraction_attempts", ["active_attempt_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_document_memory_snapshots_active_attempt_id", "document_memory_snapshots", ["active_attempt_id"])
    op.add_column("memory_extraction_candidates", sa.Column("attempt_id", postgresql.UUID(as_uuid=True)))
    op.add_column("memory_extraction_candidates", sa.Column("unresolved_scope_references", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.create_foreign_key("fk_memory_extraction_candidates_attempt", "memory_extraction_candidates", "document_memory_extraction_attempts", ["attempt_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_memory_extraction_candidates_attempt_id", "memory_extraction_candidates", ["attempt_id"])
    op.add_column("memory_scope_proposals", sa.Column("attempt_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_memory_scope_proposals_attempt", "memory_scope_proposals", "document_memory_extraction_attempts", ["attempt_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_memory_scope_proposals_attempt_id", "memory_scope_proposals", ["attempt_id"])
    op.add_column("memory_scope_proposals", sa.Column("source_term_candidate_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_memory_scope_proposals_source_term_candidate", "memory_scope_proposals", "memory_extraction_candidates", ["source_term_candidate_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_memory_scope_proposals_source_term_candidate_id", "memory_scope_proposals", ["source_term_candidate_id"])

    # Existing rows become the first immutable extraction attempt of their snapshot.
    op.execute(sa.text("""
        INSERT INTO document_memory_extraction_attempts (id, snapshot_id, attempt_number, status, next_section, feedback, trace_run_id)
        SELECT gen_random_uuid(), s.id, 1,
               CASE WHEN s.status = 'awaiting_review' THEN 'awaiting_review'
                    WHEN s.status = 'failed' THEN 'failed'
                    WHEN s.status IN ('queued', 'screening') THEN 'queued'
                    WHEN s.status IN ('studying', 'conflict_checking') THEN 'studying'
                    WHEN s.status = 'superseded' THEN 'superseded' ELSE 'completed' END,
               COALESCE((s.metrics->>'next_section')::integer, 0), '[]'::jsonb,
               COALESCE(s.trace_run_id, gen_random_uuid())
        FROM document_memory_snapshots s
    """))
    op.execute(sa.text("""
        UPDATE document_memory_snapshots s
        SET active_attempt_id = a.id
        FROM document_memory_extraction_attempts a
        WHERE a.snapshot_id = s.id AND a.attempt_number = 1
    """))
    op.execute(sa.text("""
        UPDATE memory_extraction_candidates c SET attempt_id = s.active_attempt_id
        FROM document_memory_snapshots s WHERE s.id = c.snapshot_id
    """))
    op.execute(sa.text("""
        UPDATE memory_scope_proposals p SET attempt_id = s.active_attempt_id
        FROM document_memory_snapshots s WHERE s.id = p.snapshot_id
    """))
    op.execute(sa.text("""
        UPDATE memory_scope_proposals SET source_term_candidate_id = term_candidate_id
        WHERE term_candidate_id IS NOT NULL
    """))
    op.execute(sa.text("UPDATE memory_conflict_cases SET status = 'resolved' WHERE status = 'open' AND kind IN ('duplicate', 'compatible_extension', 'scope_override')"))

    # A canonical scope may be named by many separate extraction attempts.
    op.drop_constraint("memory_scope_proposals_memory_scope_id_key", "memory_scope_proposals", type_="unique")
    op.create_index("ix_memory_scope_proposals_memory_scope_id", "memory_scope_proposals", ["memory_scope_id"])
    op.create_index("ix_memory_scope_proposals_scope_identity", "memory_scope_proposals", ["scope_type", "normalized_key", "attempt_id"])
    op.drop_constraint("ck_memory_scope_proposal_status", "memory_scope_proposals", type_="check")
    op.create_check_constraint("ck_memory_scope_proposal_status", "memory_scope_proposals", "status IN ('awaiting_term', 'needs_review', 'approved', 'rejected', 'superseded')")
    op.drop_constraint("ck_memory_candidate_scope_proposal_status", "memory_candidate_scope_proposals", type_="check")
    op.create_check_constraint("ck_memory_candidate_scope_proposal_status", "memory_candidate_scope_proposals", "status IN ('suggested', 'confirmed', 'rejected', 'superseded')")


def downgrade() -> None:
    # Preserve review history: 0176 cannot represent retries or shared scopes.
    # Fail before changing any schema rather than deleting audit records.
    op.execute(sa.text("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM document_memory_extraction_attempts WHERE attempt_number > 1)
             OR EXISTS (SELECT 1 FROM memory_scope_proposals WHERE status = 'superseded')
             OR EXISTS (SELECT 1 FROM memory_candidate_scope_proposals WHERE status = 'superseded')
             OR EXISTS (SELECT 1 FROM memory_scope_proposals WHERE memory_scope_id IS NOT NULL
                        GROUP BY memory_scope_id HAVING count(*) > 1)
             OR EXISTS (SELECT 1 FROM memory_extraction_candidates WHERE unresolved_scope_references <> '[]'::jsonb)
          THEN RAISE EXCEPTION '0177 downgrade requires compatible review history; retain 0177 to preserve audit data';
          END IF;
        END $$;
    """))
    op.drop_constraint("ck_memory_candidate_scope_proposal_status", "memory_candidate_scope_proposals", type_="check")
    op.create_check_constraint("ck_memory_candidate_scope_proposal_status", "memory_candidate_scope_proposals", "status IN ('suggested', 'confirmed', 'rejected')")
    op.drop_constraint("ck_memory_scope_proposal_status", "memory_scope_proposals", type_="check")
    op.create_check_constraint("ck_memory_scope_proposal_status", "memory_scope_proposals", "status IN ('awaiting_term', 'needs_review', 'approved', 'rejected')")
    op.drop_index("ix_memory_scope_proposals_scope_identity", table_name="memory_scope_proposals")
    op.drop_index("ix_memory_scope_proposals_memory_scope_id", table_name="memory_scope_proposals")
    op.create_unique_constraint("memory_scope_proposals_memory_scope_id_key", "memory_scope_proposals", ["memory_scope_id"])
    op.drop_index("ix_memory_scope_proposals_source_term_candidate_id", table_name="memory_scope_proposals")
    op.drop_constraint("fk_memory_scope_proposals_source_term_candidate", "memory_scope_proposals", type_="foreignkey")
    op.drop_column("memory_scope_proposals", "source_term_candidate_id")
    op.drop_constraint("fk_memory_scope_proposals_attempt", "memory_scope_proposals", type_="foreignkey")
    op.drop_index("ix_memory_scope_proposals_attempt_id", table_name="memory_scope_proposals")
    op.drop_column("memory_scope_proposals", "attempt_id")
    op.drop_index("ix_memory_extraction_candidates_attempt_id", table_name="memory_extraction_candidates")
    op.drop_constraint("fk_memory_extraction_candidates_attempt", "memory_extraction_candidates", type_="foreignkey")
    op.drop_column("memory_extraction_candidates", "attempt_id")
    op.drop_column("memory_extraction_candidates", "unresolved_scope_references")
    op.drop_index("ix_document_memory_snapshots_active_attempt_id", table_name="document_memory_snapshots")
    op.drop_constraint("fk_document_memory_snapshots_active_attempt", "document_memory_snapshots", type_="foreignkey")
    op.drop_column("document_memory_snapshots", "active_attempt_id")
    op.drop_index("ix_document_memory_attempts_status", table_name="document_memory_extraction_attempts")
    op.drop_index("ix_document_memory_extraction_attempts_snapshot_id", table_name="document_memory_extraction_attempts")
    op.drop_table("document_memory_extraction_attempts")
