"""Persist recent periodic task runs.

Revision ID: 0215
Revises: 0214
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0215"
down_revision = "0214"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("periodic_tasks", sa.Column("last_run_id", sa.String(255), nullable=True))
    op.create_table(
        "periodic_task_runs",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("periodic_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("events", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("result_limited", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_periodic_task_runs_latest", "periodic_task_runs", ["task_id", "created_at", "id"])


def downgrade() -> None:
    op.drop_table("periodic_task_runs")
    op.drop_column("periodic_tasks", "last_run_id")
