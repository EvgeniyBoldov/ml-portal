"""Persist RAG ingest stage results.

Revision ID: 0158
Revises: 0157
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0158"
down_revision = "0157"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_ingest_stage_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rag_ingest_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("input_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("output_fingerprint", sa.String(length=128), nullable=True),
        sa.Column("result_json", postgresql.JSONB(), nullable=True),
        sa.Column("metrics_json", postgresql.JSONB(), nullable=True),
        sa.Column("error_short", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("run_id", "stage_key", name="uq_rag_ingest_stage_runs_run_stage"),
    )
    op.create_index("ix_rag_ingest_stage_runs_run", "rag_ingest_stage_runs", ["run_id"])
    op.create_index("ix_rag_ingest_stage_runs_status", "rag_ingest_stage_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_rag_ingest_stage_runs_status", table_name="rag_ingest_stage_runs")
    op.drop_index("ix_rag_ingest_stage_runs_run", table_name="rag_ingest_stage_runs")
    op.drop_table("rag_ingest_stage_runs")
