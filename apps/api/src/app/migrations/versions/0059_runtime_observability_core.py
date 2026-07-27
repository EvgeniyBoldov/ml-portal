"""Persisted budgets and canonical runtime event journal."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("execution_limits", sa.Column("plan_revisions_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("task_attempts_total_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("agent_runs_total_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("llm_calls_total_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("tool_calls_total_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("tokens_total_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("execution_wall_time_ms_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("run_ttl_ms", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("planner_llm_calls_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("planner_retries_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("planner_tokens_total_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("planner_execution_wall_time_ms_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("agent_attempts_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("agent_llm_calls_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("agent_tool_calls_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("agent_tokens_total_max", sa.Integer(), nullable=True))
    op.add_column("execution_limits", sa.Column("agent_execution_wall_time_ms_max", sa.Integer(), nullable=True))
    for column in ("runtime_steps_max", "runtime_tool_calls_max", "runtime_retries_max", "runtime_wall_time_ms_max", "runtime_tokens_total_max"):
        op.drop_column("execution_limits", column)

    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.create_table("runtime_budget_counters",
        sa.Column("id", uuid, primary_key=True), sa.Column("run_id", uuid, nullable=False),
        sa.Column("owner_type", sa.String(40), nullable=False), sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False), sa.Column("consumed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("limit_value", sa.Integer(), nullable=True), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_type", "owner_id", "metric", name="uq_runtime_budget_counter"))
    op.create_index("ix_runtime_budget_counters_run_id", "runtime_budget_counters", ["run_id"])
    op.create_table("runtime_budget_entries",
        sa.Column("id", uuid, primary_key=True), sa.Column("run_id", uuid, nullable=False),
        sa.Column("owner_type", sa.String(40), nullable=False), sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("metric", sa.String(64), nullable=False), sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("before_value", sa.Integer(), nullable=False), sa.Column("after_value", sa.Integer(), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=True), sa.Column("reason", sa.String(128), nullable=False),
        sa.Column("causation_event_id", uuid, nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_runtime_budget_entry_owner", "runtime_budget_entries", ["owner_type", "owner_id", "created_at"])
    op.create_index("ix_runtime_budget_entries_run_id", "runtime_budget_entries", ["run_id"])
    op.create_table("runtime_execution_events",
        sa.Column("id", uuid, primary_key=True), sa.Column("run_id", uuid, nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=True), sa.Column("entity_id", sa.String(255), nullable=True),
        sa.Column("parent_entity_type", sa.String(40), nullable=True), sa.Column("parent_entity_id", sa.String(255), nullable=True),
        sa.Column("trigger", sa.String(128), nullable=True), sa.Column("caused_by_event_id", uuid, nullable=True),
        sa.Column("logging_level", sa.String(10), nullable=False, server_default="brief"), sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload_hash", sa.String(64), nullable=True), sa.Column("payload", jsonb, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_runtime_event_run_sequence", "runtime_execution_events", ["run_id", "sequence"])
    op.create_index("ix_runtime_execution_events_event_type", "runtime_execution_events", ["event_type"])
    op.create_table("runtime_event_sequences",
        sa.Column("run_id", uuid, primary_key=True),
        sa.Column("next_sequence", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    raise RuntimeError("runtime observability core is irreversible")
