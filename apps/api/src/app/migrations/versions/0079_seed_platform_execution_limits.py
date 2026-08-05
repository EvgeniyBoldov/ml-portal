"""Seed the mandatory platform/global execution-limit profile.

The row is a system default, not tenant data.  Entity scopes retain their
nullable override semantics and inherit from this row through the resolver.
"""

from alembic import op


revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO execution_limits (
            id, scope_type, scope_ref,
            llm_input_tokens_max, llm_output_tokens_max, llm_context_window_max, llm_timeout_s,
            plan_revisions_max, task_attempts_total_max, agent_runs_total_max,
            llm_calls_total_max, tool_calls_total_max, tokens_total_max,
            execution_wall_time_ms_max, run_ttl_ms,
            planner_llm_calls_max, planner_retries_max, planner_tokens_total_max,
            planner_execution_wall_time_ms_max, agent_attempts_max, agent_llm_calls_max,
            agent_tool_calls_max, agent_tokens_total_max,
            agent_execution_wall_time_ms_max, max_parallel_tasks,
            created_at, updated_at
        ) VALUES (
            '00000000-0000-0000-0000-000000000079', 'platform', 'global',
            16000, 4096, 16384, 30,
            25, 3, 25, 100, 50, 32000, 300000, 600000,
            12, 3, 12000, 300000, 3, 10, 50, 16000, 300000, 1,
            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        ) ON CONFLICT (scope_type, scope_ref) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM execution_limits WHERE id = '00000000-0000-0000-0000-000000000079'"
    )
