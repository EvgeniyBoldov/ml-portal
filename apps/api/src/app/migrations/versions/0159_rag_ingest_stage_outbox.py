"""Add transactional outbox for individual RAG ingest stages.

Revision ID: 0159
Revises: 0158
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0159"
down_revision = "0158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_ingest_stage_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rag_ingest_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_key", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("run_id", "stage_key", name="uq_rag_ingest_stage_outbox_run_stage"),
    )
    op.create_index("ix_rag_ingest_stage_outbox_status_available", "rag_ingest_stage_outbox", ["status", "available_at"])


def downgrade() -> None:
    op.drop_index("ix_rag_ingest_stage_outbox_status_available", table_name="rag_ingest_stage_outbox")
    op.drop_table("rag_ingest_stage_outbox")
