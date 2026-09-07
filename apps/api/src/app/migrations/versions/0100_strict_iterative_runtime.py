"""Replace the graph/revision runtime with immutable iterative execution.

Revision ID: 0100
Revises: 0097
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0100"
down_revision = "0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The retired runtime has incompatible meaning for every lifecycle row.
    # Deliberately discard it instead of preserving a misleading adapter.
    for table in (
        "runtime_planner_invocations", "runtime_plan_revisions", "runtime_task_attempts", "runtime_task_needs",
        "runtime_task_dependencies", "runtime_plan_stages", "runtime_plan_tasks", "runtime_plans",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.alter_column("execution_limits", "plan_revisions_max", new_column_name="iterations_max")
    op.alter_column("runtime_execution_limits", "max_replans", new_column_name="max_iterations")
    op.get_bind().execute(sa.text(
        "UPDATE system_llm_roles SET rules = :rules WHERE role_type = 'planner' AND is_active = true"
    ), {"rules": (
        "Верни строгий JSON IterationProposal. Задачи всегда агентские; terminal=planner "
        "создаёт следующую iteration, terminal=synthesis завершает run и требует synthesis_brief. "
        "Не создавай checkpoint-задачи, patch, revision, ask_user или fail. При неуспешных "
        "задачах runtime вернёт управление planner; рассмотри их через explicit resolutions."
    )})
    op.get_bind().execute(sa.text(
        "UPDATE system_llm_roles SET rules = :rules WHERE role_type = 'synthesizer' AND is_active = true"
    ), {"rules": (
        "Следуй synthesis brief. Используй только completed reports, явно принятые partial outputs "
        "и verified sources; limitations содержат только актуальные пользовательские ограничения."
    )})
    op.create_table(
        "runtime_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("root_run_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("last_failure", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('draft', 'active', 'waiting_input', 'completed', 'failed', 'cancelled')", name="ck_runtime_plan_status"),
    )
    op.create_index("ix_runtime_plans_tenant_id", "runtime_plans", ["tenant_id"])
    op.create_index("ix_runtime_plans_chat_id", "runtime_plans", ["chat_id"])
    op.create_index("ix_runtime_plans_status", "runtime_plans", ["status"])
    op.create_table(
        "runtime_plan_iterations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runtime_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("terminal", sa.String(32), nullable=False),
        sa.Column("synthesis_brief", postgresql.JSONB(), nullable=True),
        sa.Column("proposal", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("checkpoint_status", sa.String(32), nullable=False, server_default="idle"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("plan_id", "sequence", name="uq_runtime_plan_iteration_sequence"),
        sa.CheckConstraint("terminal IN ('planner', 'synthesis')", name="ck_runtime_iteration_terminal"),
        sa.CheckConstraint("status IN ('active', 'closed')", name="ck_runtime_iteration_status"),
        sa.CheckConstraint("checkpoint_status IN ('idle', 'planner_running', 'synthesis_running', 'completed')", name="ck_runtime_iteration_checkpoint_status"),
    )
    op.create_index("ix_runtime_plan_iteration_active", "runtime_plan_iterations", ["plan_id", "status"])
    op.execute("CREATE UNIQUE INDEX uq_runtime_one_active_iteration ON runtime_plan_iterations(plan_id) WHERE status = 'active'")
    op.create_table(
        "runtime_plan_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runtime_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("iteration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runtime_plan_iterations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_id", sa.String(255), nullable=False),
        sa.Column("planned_order", sa.Integer(), nullable=False),
        sa.Column("intent", sa.String(512), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("executor", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("inputs", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("expected_outputs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("freshness_policy", sa.String(32), nullable=False, server_default="allow_memory"),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("plan_id", "task_id", name="uq_runtime_plan_task_id"),
        sa.CheckConstraint("status IN ('pending', 'running', 'waiting_retry', 'waiting_confirmation', 'completed', 'needs_dependency', 'unfulfillable', 'failed', 'blocked', 'cancelled')", name="ck_runtime_task_status"),
    )
    op.create_index("ix_runtime_plan_tasks_ready", "runtime_plan_tasks", ["iteration_id", "status"])
    op.create_table("runtime_task_dependencies", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("task_row_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runtime_plan_tasks.id", ondelete="CASCADE"), nullable=False), sa.Column("depends_on_task_id", sa.String(255), nullable=False), sa.UniqueConstraint("task_row_id", "depends_on_task_id", name="uq_runtime_task_dependency"))
    op.create_table("runtime_task_needs", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("task_row_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runtime_plan_tasks.id", ondelete="CASCADE"), nullable=False), sa.Column("need_ref", sa.String(255), nullable=False), sa.Column("need_key", sa.String(255), nullable=False), sa.Column("kind", sa.String(32), nullable=False), sa.Column("description", sa.Text(), nullable=False), sa.Column("schema", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("true")), sa.UniqueConstraint("task_row_id", "need_ref", name="uq_runtime_task_need"))
    op.create_table("runtime_need_bindings", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runtime_plans.id", ondelete="CASCADE"), nullable=False), sa.Column("need_task_id", sa.String(255), nullable=False), sa.Column("need_ref", sa.String(255), nullable=False), sa.Column("producer_task_id", sa.String(255), nullable=False), sa.Column("output_key", sa.String(255), nullable=False), sa.Column("consumer_task_id", sa.String(255), nullable=False), sa.Column("consumer_input_key", sa.String(255), nullable=False), sa.UniqueConstraint("consumer_task_id", "consumer_input_key", name="uq_runtime_need_binding_input"))
    op.create_table("runtime_task_resolutions", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("iteration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runtime_plan_iterations.id", ondelete="CASCADE"), nullable=False), sa.Column("task_id", sa.String(255), nullable=False), sa.Column("action", sa.String(32), nullable=False), sa.Column("output_keys", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("replacement_task_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")), sa.Column("reason", sa.Text(), nullable=False), sa.UniqueConstraint("iteration_id", "task_id", name="uq_runtime_task_resolution"))
    op.create_table("runtime_task_attempts", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("task_row_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runtime_plan_tasks.id", ondelete="CASCADE"), nullable=False), sa.Column("attempt_number", sa.Integer(), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="running"), sa.Column("execution_result", postgresql.JSONB(), nullable=True), sa.Column("error", postgresql.JSONB(), nullable=True), sa.Column("agent_execution_id", postgresql.UUID(as_uuid=True), nullable=True), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True), sa.UniqueConstraint("task_row_id", "attempt_number", name="uq_runtime_task_attempt"))
    op.create_table("runtime_pauses", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("runtime_plans.id", ondelete="CASCADE"), nullable=False), sa.Column("task_id", sa.String(255), nullable=False), sa.Column("kind", sa.String(32), nullable=False), sa.Column("operation_fingerprint", sa.String(255), nullable=False), sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")), sa.Column("status", sa.String(32), nullable=False, server_default="waiting"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("CREATE UNIQUE INDEX uq_runtime_waiting_task_pause ON runtime_pauses(plan_id, task_id) WHERE status = 'waiting'")


def downgrade() -> None:
    raise RuntimeError("strict iterative runtime migration is irreversible")
