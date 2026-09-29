"""Reconcile RAG document lifecycle projection with aggregate status graph.

Revision ID: 0160
Revises: 0159
"""
from __future__ import annotations

from alembic import op


revision = "0160"
down_revision = "0159"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ``ragdocuments.status`` predates the node-level status graph.  Bring the
    # persisted lifecycle projection in sync for rows that already have an
    # aggregate, without introducing new values to the PostgreSQL enum.
    op.execute("""
        UPDATE ragdocuments
        SET status = CASE agg_status
            WHEN 'uploaded' THEN 'uploaded'::documentstatus
            WHEN 'processing' THEN 'processing'::documentstatus
            WHEN 'ready' THEN 'ready'::documentstatus
            WHEN 'partial' THEN 'processed'::documentstatus
            WHEN 'failed' THEN 'failed'::documentstatus
            WHEN 'archived' THEN 'archived'::documentstatus
            ELSE status
        END
        WHERE agg_status IN ('uploaded', 'processing', 'ready', 'partial', 'failed', 'archived')
    """)


def downgrade() -> None:
    # This is a data reconciliation; the previous lifecycle value is not
    # recoverable once replaced.
    pass
