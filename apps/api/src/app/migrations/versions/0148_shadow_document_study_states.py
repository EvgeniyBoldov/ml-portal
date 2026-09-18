"""Prepare document-memory snapshots for the shadow study workflow.

Revision ID: 0148
Revises: 0147
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0148"
down_revision = "0147"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # P0 snapshots were produced by the compatibility backfill.  They do not
    # represent a completed shadow review and must never be confused with one.
    op.execute("UPDATE document_memory_snapshots SET status = 'backfilled' WHERE status = 'completed'")
    op.drop_constraint("ck_document_memory_snapshot_state", "document_memory_snapshots", type_="check")
    op.create_check_constraint(
        "ck_document_memory_snapshot_state",
        "document_memory_snapshots",
        "status IN ('queued', 'screening', 'studying', 'ready_for_review', 'skipped', 'failed', 'superseded', 'backfilled')",
    )
    op.alter_column(
        "document_memory_snapshots",
        "status",
        existing_type=sa.String(length=16),
        type_=sa.String(length=24),
        server_default="queued",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute("UPDATE document_memory_snapshots SET status = 'completed' WHERE status IN ('queued', 'screening', 'studying', 'ready_for_review', 'skipped', 'backfilled')")
    op.drop_constraint("ck_document_memory_snapshot_state", "document_memory_snapshots", type_="check")
    op.create_check_constraint(
        "ck_document_memory_snapshot_state",
        "document_memory_snapshots",
        "status IN ('completed', 'failed', 'superseded')",
    )
    op.alter_column(
        "document_memory_snapshots",
        "status",
        existing_type=sa.String(length=24),
        type_=sa.String(length=16),
        server_default="completed",
        existing_nullable=False,
    )
