"""Add runtime budget defaults to platform_settings and backfill.

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_settings", sa.Column("budget_max_planner_iterations", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("budget_max_agent_steps", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("budget_max_tool_calls_total", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("budget_max_wall_time_ms", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("budget_per_tool_timeout_ms", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("budget_max_steps_without_success", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("budget_loop_threshold", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("budget_max_retries", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("budget_max_tokens_total", sa.Integer(), nullable=True))

    # Backfill only NULL values with canonical defaults.
    op.execute("""
        UPDATE platform_settings
        SET
          budget_max_planner_iterations = COALESCE(budget_max_planner_iterations, 12),
          budget_max_agent_steps = COALESCE(budget_max_agent_steps, 20),
          budget_max_tool_calls_total = COALESCE(budget_max_tool_calls_total, 50),
          budget_max_wall_time_ms = COALESCE(budget_max_wall_time_ms, 120000),
          budget_per_tool_timeout_ms = COALESCE(budget_per_tool_timeout_ms, 30000),
          budget_max_steps_without_success = COALESCE(budget_max_steps_without_success, 2),
          budget_loop_threshold = COALESCE(budget_loop_threshold, 3),
          budget_max_retries = COALESCE(budget_max_retries, 3)
    """)


def downgrade() -> None:
    op.drop_column("platform_settings", "budget_max_tokens_total")
    op.drop_column("platform_settings", "budget_max_retries")
    op.drop_column("platform_settings", "budget_loop_threshold")
    op.drop_column("platform_settings", "budget_max_steps_without_success")
    op.drop_column("platform_settings", "budget_per_tool_timeout_ms")
    op.drop_column("platform_settings", "budget_max_wall_time_ms")
    op.drop_column("platform_settings", "budget_max_tool_calls_total")
    op.drop_column("platform_settings", "budget_max_agent_steps")
    op.drop_column("platform_settings", "budget_max_planner_iterations")
