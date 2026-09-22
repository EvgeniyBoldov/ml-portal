"""Add durable RAG ingest runs and transactional dispatch outbox.

Revision ID: 0157
Revises: 0156
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0157"
down_revision = "0156"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ragdocuments", sa.Column("ingest_generation", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "rag_ingest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("target_models", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("resume_stage", sa.String(length=64), nullable=True),
        sa.Column("error_short", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("doc_id", "generation", name="uq_rag_ingest_runs_doc_generation"),
    )
    op.create_index("ix_rag_ingest_runs_doc_id", "rag_ingest_runs", ["doc_id"])
    op.create_index("ix_rag_ingest_runs_status", "rag_ingest_runs", ["status"])
    op.create_table(
        "rag_ingest_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rag_ingest_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("command", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("celery_task_id", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("run_id", name="uq_rag_ingest_outbox_run"),
    )
    op.create_index("ix_rag_ingest_outbox_status_available", "rag_ingest_outbox", ["status", "available_at"])


def downgrade() -> None:
    op.drop_index("ix_rag_ingest_outbox_status_available", table_name="rag_ingest_outbox")
    op.drop_table("rag_ingest_outbox")
    op.drop_index("ix_rag_ingest_runs_status", table_name="rag_ingest_runs")
    op.drop_index("ix_rag_ingest_runs_doc_id", table_name="rag_ingest_runs")
    op.drop_table("rag_ingest_runs")
    op.drop_column("ragdocuments", "ingest_generation")
