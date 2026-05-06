"""Add execution limit overrides to agents table and drop unused limits tables.

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-06

Changes:
- agents: add max_steps, timeout_s, max_retries (nullable overrides)
- drop limit_versions table
- drop limits table
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add execution limit override columns to agents
    op.add_column(
        "agents",
        sa.Column(
            "max_steps",
            sa.Integer(),
            nullable=True,
            comment="Max agent loop steps override (-> orchestration executor_max_steps if None)",
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "timeout_s",
            sa.Integer(),
            nullable=True,
            comment="Per-run wall time limit in seconds override (-> orchestration executor_timeout_s if None)",
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "max_retries",
            sa.Integer(),
            nullable=True,
            comment="Max tool call retries override (-> orchestration default if None)",
        ),
    )

    # 2. Drop unused limits tables (was never connected to runtime)
    op.drop_table("limit_versions")
    op.drop_table("limits")


def downgrade() -> None:
    # Restore limits tables
    op.create_table(
        "limits",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "limit_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("limit_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("max_steps", sa.Integer(), nullable=True),
        sa.Column("max_tool_calls", sa.Integer(), nullable=True),
        sa.Column("max_wall_time_ms", sa.Integer(), nullable=True),
        sa.Column("tool_timeout_ms", sa.Integer(), nullable=True),
        sa.Column("max_retries", sa.Integer(), nullable=True),
        sa.Column("extra_config", sa.JSON(), nullable=False),
        sa.Column("parent_version_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["limit_id"], ["limits.id"], ondelete="CASCADE"),
    )

    # Remove columns from agents
    op.drop_column("agents", "max_retries")
    op.drop_column("agents", "timeout_s")
    op.drop_column("agents", "max_steps")
