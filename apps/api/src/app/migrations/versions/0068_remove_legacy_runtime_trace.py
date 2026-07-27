"""Remove obsolete AgentRun and routing-log persistence.

The legacy records are intentionally discarded.  Canonical runtime history is
``runtime_execution_events``; this revision performs schema removal only and
does not backfill old user or tenant data.
"""
from alembic import op


revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CASCADE removes only foreign keys targeting these obsolete tables.
    op.execute("DROP TABLE IF EXISTS agent_run_steps CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS routing_logs CASCADE")
    op.execute("ALTER TABLE chat_turns DROP COLUMN IF EXISTS agent_run_id")
    op.alter_column("runtime_task_attempts", "agent_run_id", new_column_name="agent_execution_id")


def downgrade() -> None:
    raise RuntimeError("legacy runtime trace removal is irreversible")
