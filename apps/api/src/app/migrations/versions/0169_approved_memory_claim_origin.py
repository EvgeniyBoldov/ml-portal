"""Link published memory claims to approved extraction candidates.

Revision ID: 0169
Revises: 0168
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0169"
down_revision = "0168"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memory_claims", sa.Column("approved_candidate_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_memory_claims_approved_candidate", "memory_claims", "memory_extraction_candidates",
                          ["approved_candidate_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_memory_claims_approved_candidate_id", "memory_claims", ["approved_candidate_id"])
    # Preserve already approved publications when the source match is unique.
    op.execute(sa.text("""
        WITH matches AS (
            SELECT claim.id AS claim_id,
                   max(candidate.id::text)::uuid AS candidate_id
            FROM memory_claims AS claim
            JOIN document_memory_snapshots AS snapshot
              ON snapshot.document_id = claim.document_id
             AND snapshot.canonical_checksum = claim.canonical_checksum
            JOIN memory_extraction_candidates AS candidate
              ON candidate.snapshot_id = snapshot.id
             AND candidate.candidate_type = claim.item_type
             AND candidate.normalized_subject = claim.normalized_subject
             AND candidate.resolution_status = 'resolved'
            JOIN memory_candidate_decisions AS decision
              ON decision.candidate_id = candidate.id
             AND decision.action IN ('approve', 'autoapprove')
             AND (
                 (decision.payload->>'scope' = 'global' AND claim.scope = 'company' AND claim.scope_signature = 'legacy')
                 OR (decision.payload->>'scope' = 'project' AND claim.scope = 'project' AND claim.scope_signature = 'legacy')
                 OR (decision.payload->>'scope' = 'scoped' AND claim.scope_signature <> 'legacy')
             )
            GROUP BY claim.id
            HAVING count(DISTINCT candidate.id) = 1
        )
        UPDATE memory_claims AS claim
        SET approved_candidate_id = matches.candidate_id
        FROM matches
        WHERE claim.id = matches.claim_id
    """))


def downgrade() -> None:
    op.drop_index("ix_memory_claims_approved_candidate_id", table_name="memory_claims")
    op.drop_constraint("fk_memory_claims_approved_candidate", "memory_claims", type_="foreignkey")
    op.drop_column("memory_claims", "approved_candidate_id")
