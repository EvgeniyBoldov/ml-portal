"""Add unified execution_limits table.

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_limits",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope_type", sa.String(length=50), nullable=False),
        sa.Column("scope_ref", sa.String(length=255), nullable=False),
        sa.Column("llm_input_tokens_max", sa.Integer(), nullable=True),
        sa.Column("llm_output_tokens_max", sa.Integer(), nullable=True),
        sa.Column("llm_context_window_max", sa.Integer(), nullable=True),
        sa.Column("runtime_steps_max", sa.Integer(), nullable=True),
        sa.Column("runtime_tool_calls_max", sa.Integer(), nullable=True),
        sa.Column("runtime_retries_max", sa.Integer(), nullable=True),
        sa.Column("runtime_wall_time_ms_max", sa.Integer(), nullable=True),
        sa.Column("runtime_tokens_total_max", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_type", "scope_ref", name="uq_execution_limits_scope"),
    )
    op.create_index("ix_execution_limits_scope_type", "execution_limits", ["scope_type"], unique=False)
    op.create_index("ix_execution_limits_scope_ref", "execution_limits", ["scope_ref"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_execution_limits_scope_ref", table_name="execution_limits")
    op.drop_index("ix_execution_limits_scope_type", table_name="execution_limits")
    op.drop_table("execution_limits")

