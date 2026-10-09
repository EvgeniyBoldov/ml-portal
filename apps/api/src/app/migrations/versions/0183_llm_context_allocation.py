"""Move output allocation from actors to the LLM connector.

Revision ID: 0183
Revises: 0182
"""
from alembic import op
import sqlalchemy as sa

revision = "0183"
down_revision = "0182"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("models", sa.Column("context_window_tokens", sa.Integer(), nullable=False, server_default="16384"))
    op.create_check_constraint("ck_models_context_window_positive", "models", "context_window_tokens > 0")
    op.drop_table("execution_limits")
    op.execute("ALTER TABLE IF EXISTS limit_versions DROP COLUMN IF EXISTS max_tokens_total")
    op.drop_column("models", "max_output_tokens")
    op.drop_column("system_llm_roles", "max_tokens")
    op.drop_column("system_llm_roles", "timeout_s")
    op.drop_column("system_llm_roles", "max_retries")
    op.drop_column("system_llm_roles", "retry_backoff")
    # Provider-specific JSON must not resurrect the removed output limit.
    op.execute("UPDATE models SET extra_config = (extra_config::jsonb - 'max_tokens' - 'max_output_tokens')::json WHERE jsonb_typeof(extra_config::jsonb) = 'object'")


def downgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS limit_versions ADD COLUMN IF NOT EXISTS max_tokens_total INTEGER")
    op.create_table(
        "execution_limits",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("scope_type", sa.String(50), nullable=False),
        sa.Column("scope_ref", sa.String(255), nullable=False),
        sa.Column("iterations_max", sa.Integer(), nullable=True),
        sa.Column("task_attempts_total_max", sa.Integer(), nullable=True),
        sa.Column("agent_runs_total_max", sa.Integer(), nullable=True),
        sa.Column("llm_calls_total_max", sa.Integer(), nullable=True),
        sa.Column("tool_calls_total_max", sa.Integer(), nullable=True),
        sa.Column("tokens_total_max", sa.Integer(), nullable=True),
        sa.Column("execution_wall_time_ms_max", sa.Integer(), nullable=True),
        sa.Column("run_ttl_ms", sa.Integer(), nullable=True),
        sa.Column("planner_llm_calls_max", sa.Integer(), nullable=True),
        sa.Column("planner_retries_max", sa.Integer(), nullable=True),
        sa.Column("planner_tokens_total_max", sa.Integer(), nullable=True),
        sa.Column("planner_execution_wall_time_ms_max", sa.Integer(), nullable=True),
        sa.Column("agent_attempts_max", sa.Integer(), nullable=True),
        sa.Column("agent_llm_calls_max", sa.Integer(), nullable=True),
        sa.Column("agent_tool_calls_max", sa.Integer(), nullable=True),
        sa.Column("agent_tokens_total_max", sa.Integer(), nullable=True),
        sa.Column("agent_execution_wall_time_ms_max", sa.Integer(), nullable=True),
        sa.Column("max_parallel_tasks", sa.Integer(), nullable=True),
        sa.Column("llm_input_tokens_max", sa.Integer(), nullable=True),
        sa.Column("llm_output_tokens_max", sa.Integer(), nullable=True),
        sa.Column("llm_context_window_max", sa.Integer(), nullable=True),
        sa.Column("llm_timeout_s", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope_type", "scope_ref", name="uq_execution_limits_scope"),
    )
    op.create_index("ix_execution_limits_scope_type", "execution_limits", ["scope_type"])
    op.create_index("ix_execution_limits_scope_ref", "execution_limits", ["scope_ref"])
    op.add_column("system_llm_roles", sa.Column("max_tokens", sa.Integer(), nullable=True))
    op.add_column("system_llm_roles", sa.Column("timeout_s", sa.Integer(), nullable=True))
    op.add_column("system_llm_roles", sa.Column("max_retries", sa.Integer(), nullable=True))
    op.add_column("system_llm_roles", sa.Column("retry_backoff", sa.String(10), nullable=True))
    op.create_check_constraint("check_retry_backoff_type", "system_llm_roles", "retry_backoff IN ('none', 'linear', 'exp')")
    op.add_column("models", sa.Column("max_output_tokens", sa.Integer(), nullable=True))
    op.drop_constraint("ck_models_context_window_positive", "models", type_="check")
    op.drop_column("models", "context_window_tokens")
