"""Persist planner invocation boundaries for the runtime inspector."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "runtime_planner_invocations",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("run_id", uuid, nullable=False),
        sa.Column("orchestrator_id", sa.String(255), nullable=False),
        sa.Column("plan_id", uuid, nullable=True),
        sa.Column("trigger", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("revision_before", sa.Integer(), nullable=True),
        sa.Column("revision_after", sa.Integer(), nullable=True),
        sa.Column("context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_runtime_planner_invocations_run_id", "runtime_planner_invocations", ["run_id"])
    op.create_index("ix_runtime_planner_invocations_plan_id", "runtime_planner_invocations", ["plan_id"])


def downgrade() -> None:
    raise RuntimeError("planner invocation storage is irreversible")
