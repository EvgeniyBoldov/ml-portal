"""Drop legacy limit columns after execution_limits rollout.

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-22
"""

from alembic import op


revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # agents
    op.drop_column("agents", "max_tokens")
    op.drop_column("agents", "max_steps")
    op.drop_column("agents", "timeout_s")
    op.drop_column("agents", "max_retries")

    # orchestration_settings
    op.drop_column("orchestration_settings", "executor_timeout_s")
    op.drop_column("orchestration_settings", "executor_max_steps")
    op.drop_column("orchestration_settings", "executor_max_retries")

    # platform_settings
    op.drop_column("platform_settings", "abs_max_timeout_s")
    op.drop_column("platform_settings", "abs_max_retries")
    op.drop_column("platform_settings", "abs_max_steps")
    op.drop_column("platform_settings", "budget_max_planner_iterations")
    op.drop_column("platform_settings", "budget_max_agent_steps")
    op.drop_column("platform_settings", "budget_max_tool_calls_total")
    op.drop_column("platform_settings", "budget_max_wall_time_ms")
    op.drop_column("platform_settings", "budget_per_tool_timeout_ms")
    op.drop_column("platform_settings", "budget_max_steps_without_success")
    op.drop_column("platform_settings", "budget_loop_threshold")
    op.drop_column("platform_settings", "budget_max_retries")
    op.drop_column("platform_settings", "budget_max_tokens_total")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for 0030_drop_legacy_limit_columns")
