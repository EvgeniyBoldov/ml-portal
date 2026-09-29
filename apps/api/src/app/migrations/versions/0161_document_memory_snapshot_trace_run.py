"""Attach document-memory snapshots to their runtime journal explicitly.

Revision ID: 0161
Revises: 0160
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0161"
down_revision = "0160"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_memory_snapshots",
        sa.Column("trace_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_document_memory_snapshots_trace_run_id",
        "document_memory_snapshots",
        ["trace_run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_memory_snapshots_trace_run_id", table_name="document_memory_snapshots")
    op.drop_column("document_memory_snapshots", "trace_run_id")
