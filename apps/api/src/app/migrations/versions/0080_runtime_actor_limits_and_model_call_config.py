"""Replace legacy execution-limit contracts with runtime and actor groups.

The legacy table is retained in this revision so existing user overrides are
not destroyed by a schema deployment. Runtime no longer reads it.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "runtime_execution_limits",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("scope_ref", sa.String(32), nullable=False, unique=True),
        sa.Column("wall_time_ms_max", sa.Integer(), nullable=True),
        sa.Column("max_parallel_tasks", sa.Integer(), nullable=True),
        sa.Column("max_replans", sa.Integer(), nullable=True),
        sa.Column("max_task_executions", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "actor_execution_limits",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("scope_type", sa.String(50), nullable=False),
        sa.Column("scope_ref", sa.String(255), nullable=False),
        sa.Column("llm_calls_max", sa.Integer(), nullable=True),
        sa.Column("tool_calls_max", sa.Integer(), nullable=True),
        sa.Column("wall_time_ms_max", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("scope_type", "scope_ref", name="uq_actor_execution_limits_scope"),
    )
    op.create_index("ix_actor_execution_limits_scope_type", "actor_execution_limits", ["scope_type"])
    op.create_index("ix_actor_execution_limits_scope_ref", "actor_execution_limits", ["scope_ref"])
    op.add_column("models", sa.Column("max_output_tokens", sa.Integer(), nullable=True))
    op.add_column("models", sa.Column("request_timeout_s", sa.Integer(), nullable=True))
    op.add_column("models", sa.Column("max_retries", sa.Integer(), nullable=True))
    # Required platform defaults only; no tenant or user-specific rows are
    # migrated from the legacy table.
    op.execute(
        """
        INSERT INTO runtime_execution_limits
            (id, scope_ref, wall_time_ms_max, max_parallel_tasks, max_replans, max_task_executions, created_at, updated_at)
        VALUES
            ('00000000-0000-0000-0000-000000000080', 'global', 300000, 1, 3, 100, now(), now())
        ON CONFLICT (scope_ref) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO actor_execution_limits
            (id, scope_type, scope_ref, llm_calls_max, tool_calls_max, wall_time_ms_max, created_at, updated_at)
        VALUES
            ('00000000-0000-0000-0000-000000000081', 'agent_default', 'global', 10, 50, 300000, now(), now()),
            ('00000000-0000-0000-0000-000000000082', 'orchestrator_default', 'global', 12, NULL, 300000, now(), now())
        ON CONFLICT (scope_type, scope_ref) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_column("models", "max_retries")
    op.drop_column("models", "request_timeout_s")
    op.drop_column("models", "max_output_tokens")
    op.drop_index("ix_actor_execution_limits_scope_ref", table_name="actor_execution_limits")
    op.drop_index("ix_actor_execution_limits_scope_type", table_name="actor_execution_limits")
    op.drop_table("actor_execution_limits")
    op.drop_table("runtime_execution_limits")
