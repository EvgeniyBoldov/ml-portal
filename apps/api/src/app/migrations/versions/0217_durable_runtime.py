"""Add durable runtime execution and delivery state.

Revision ID: 0217
Revises: 0216
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0217"
down_revision = "0216"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_runtime_plan_status", "runtime_plans", type_="check")
    op.create_check_constraint(
        "ck_runtime_plan_status", "runtime_plans",
        "status IN ('draft', 'active', 'waiting_input', 'waiting_timer', 'completed', 'failed', 'cancelled')",
    )
    op.create_table(
        "durable_runtime_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_turn_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("chat_turns.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("admission_key", sa.String(255), nullable=True, unique=True),
        sa.Column("request_payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("recipient", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_durable_runtime_runs_owner_user_id", "durable_runtime_runs", ["owner_user_id"])
    op.create_index("ix_durable_runtime_runs_status", "durable_runtime_runs", ["status"])
    op.create_table(
        "durable_runtime_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("durable_runtime_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("reason", sa.String(32), nullable=False, server_default="initial"),
        sa.Column("pause_id", postgresql.UUID(as_uuid=True), nullable=True, unique=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True), sa.Column("worker_id", sa.String(255), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True), sa.Column("attempt", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_error", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "sequence", name="uq_durable_runtime_segment_sequence"),
    )
    op.create_index("ix_durable_runtime_segments_run_id", "durable_runtime_segments", ["run_id"])
    op.create_index("ix_durable_runtime_segments_status", "durable_runtime_segments", ["status"])
    op.create_index("ix_durable_runtime_segments_ready", "durable_runtime_segments", ["status", "available_at"])
    op.create_index("ix_durable_runtime_segments_lease", "durable_runtime_segments", ["status", "lease_until"])
    op.create_index("uq_durable_runtime_segment_open", "durable_runtime_segments", ["run_id"], unique=True, postgresql_where=sa.text("status IN ('queued', 'running')"))
    op.create_table(
        "durable_runtime_pauses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("durable_runtime_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False), sa.Column("requester", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("wake_at", sa.DateTime(timezone=True), nullable=True), sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_durable_runtime_pauses_run_id", "durable_runtime_pauses", ["run_id"])
    op.create_index("ix_durable_runtime_pauses_wake_at", "durable_runtime_pauses", ["wake_at"])
    op.create_index("ix_durable_runtime_pauses_active", "durable_runtime_pauses", ["run_id", "status"])
    op.create_index("uq_durable_runtime_pause_open", "durable_runtime_pauses", ["run_id"], unique=True, postgresql_where=sa.text("status = 'active'"))
    op.create_table(
        "durable_runtime_commands",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("durable_runtime_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_key", sa.String(255), nullable=False), sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True), sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("run_id", "event_key", name="uq_durable_runtime_command_event"),
    )
    op.create_index("ix_durable_runtime_commands_run_id", "durable_runtime_commands", ["run_id"])
    op.create_table(
        "durable_runtime_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("durable_runtime_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("event_key", sa.String(255), nullable=False), sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("recipient", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"), sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True), sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("external_message_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "sequence", name="uq_durable_runtime_event_sequence"), sa.UniqueConstraint("run_id", "event_key", name="uq_durable_runtime_event_key"),
    )
    op.create_index("ix_durable_runtime_events_run_id", "durable_runtime_events", ["run_id"])
    op.create_index("ix_durable_runtime_events_delivery", "durable_runtime_events", ["status", "available_at"])


def downgrade() -> None:
    op.drop_table("durable_runtime_events")
    op.drop_table("durable_runtime_commands")
    op.drop_table("durable_runtime_pauses")
    op.drop_table("durable_runtime_segments")
    op.drop_table("durable_runtime_runs")
    op.drop_constraint("ck_runtime_plan_status", "runtime_plans", type_="check")
    op.create_check_constraint(
        "ck_runtime_plan_status", "runtime_plans",
        "status IN ('draft', 'active', 'waiting_input', 'completed', 'failed', 'cancelled')",
    )
