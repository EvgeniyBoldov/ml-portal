"""Agent observability: logging_level, context_snapshot, total_llm_calls, step error

Revision ID: 0068_agent_observability
Revises: 0068
Create Date: 2026-02-13

Adds:
- agents.logging_level (none/brief/full) — replaces enable_logging boolean
- agent_runs.logging_level — copied from agent at run start
- agent_runs.context_snapshot (JSONB) — frozen versions/config for reproducibility
- agent_runs.total_llm_calls — count of LLM requests per run
- agent_run_steps.error — error message per step
- agent_run_steps.step_type index (if missing)
- Drops agents.enable_logging (replaced by logging_level)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0068_agent_observability"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. agents: add logging_level, drop enable_logging
    op.add_column(
        "agents",
        sa.Column(
            "logging_level",
            sa.String(10),
            nullable=False,
            server_default="brief",
        ),
    )

    # Migrate enable_logging → logging_level if column exists
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("agents")]
    if "enable_logging" in columns:
        op.execute(
            "UPDATE agents SET logging_level = CASE "
            "WHEN enable_logging = true THEN 'brief' "
            "ELSE 'none' END"
        )
        op.drop_column("agents", "enable_logging")

    # 2. agent_runs: add logging_level, context_snapshot, total_llm_calls
    op.add_column(
        "agent_runs",
        sa.Column(
            "logging_level",
            sa.String(10),
            nullable=False,
            server_default="brief",
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column("context_snapshot", JSONB, nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column(
            "total_llm_calls",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    # 3. agent_run_steps: add error column
    op.add_column(
        "agent_run_steps",
        sa.Column("error", sa.Text(), nullable=True),
    )

    # 4. Ensure step_type index exists
    try:
        op.create_index(
            "ix_agent_run_steps_step_type",
            "agent_run_steps",
            ["step_type"],
        )
    except Exception:
        pass  # Index may already exist from 0030

    # 5. Composite index for run filtering
    op.create_index(
        "ix_agent_runs_agent_started",
        "agent_runs",
        ["agent_slug", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_runs_agent_started", table_name="agent_runs")

    op.drop_column("agent_run_steps", "error")
    op.drop_column("agent_runs", "total_llm_calls")
    op.drop_column("agent_runs", "context_snapshot")
    op.drop_column("agent_runs", "logging_level")

    # Restore enable_logging
    op.add_column(
        "agents",
        sa.Column("enable_logging", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.drop_column("agents", "logging_level")
