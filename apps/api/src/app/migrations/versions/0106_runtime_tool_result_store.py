"""Persist runtime-owned operation results for task attempts.

Revision ID: 0106
Revises: 0105
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0106"
down_revision = "0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runtime_tool_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runtime_task_attempts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("result_ref", sa.String(length=64), nullable=False),
        sa.Column("call_id", sa.String(length=255), nullable=False),
        sa.Column("operation", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("result_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("attempt_id", "result_ref", name="uq_runtime_tool_result_ref"),
    )
    op.create_index("ix_runtime_tool_results_attempt_id", "runtime_tool_results", ["attempt_id"])
    op.create_index("ix_runtime_tool_results_expires_at", "runtime_tool_results", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_runtime_tool_results_expires_at", table_name="runtime_tool_results")
    op.drop_index("ix_runtime_tool_results_attempt_id", table_name="runtime_tool_results")
    op.drop_table("runtime_tool_results")
