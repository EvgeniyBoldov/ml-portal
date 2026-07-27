"""canonical persisted runtime plan graph

Revision ID: 0055
Revises: 0054
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def _uuid():
    return postgresql.UUID(as_uuid=True)


def _json():
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "runtime_plans",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("tenant_id", _uuid(), nullable=False),
        sa.Column("chat_id", _uuid(), nullable=True),
        sa.Column("root_run_id", _uuid(), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("answer_brief", sa.Text(), nullable=True),
        sa.Column("last_failure", _json(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("root_run_id", name="uq_runtime_plans_root_run"),
    )
    op.create_index("ix_runtime_plans_tenant_id", "runtime_plans", ["tenant_id"])
    op.create_index("ix_runtime_plans_chat_id", "runtime_plans", ["chat_id"])
    op.create_index("ix_runtime_plans_root_run_id", "runtime_plans", ["root_run_id"])
    op.create_index("ix_runtime_plans_status", "runtime_plans", ["status"])

    op.create_table(
        "runtime_plan_tasks",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("plan_id", _uuid(), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("agent_slug", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("inputs", _json(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("expected_outputs", _json(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("checkpoint", _json(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result", _json(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["runtime_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "task_id", name="uq_runtime_plan_task_id"),
    )
    op.create_index("ix_runtime_plan_tasks_ready", "runtime_plan_tasks", ["plan_id", "status"])
    op.create_index(
        "uq_runtime_plan_one_running",
        "runtime_plan_tasks",
        ["plan_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )

    op.create_table(
        "runtime_task_dependencies",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("plan_id", _uuid(), nullable=False),
        sa.Column("task_id", sa.String(length=255), nullable=False),
        sa.Column("depends_on_task_id", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["runtime_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "task_id", "depends_on_task_id", name="uq_runtime_task_dependency"),
    )

    op.create_table(
        "runtime_task_requirements",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("task_row_id", _uuid(), nullable=False),
        sa.Column("requirement_key", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="data"),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("schema", _json(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("resolved_value", _json(), nullable=True),
        sa.Column("resolver_task_id", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["task_row_id"], ["runtime_plan_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_row_id", "requirement_key", name="uq_runtime_task_requirement"),
    )
    op.create_index("ix_runtime_task_requirements_status", "runtime_task_requirements", ["status"])

    op.create_table(
        "runtime_plan_revisions",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("plan_id", _uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("patch", _json(), nullable=False),
        sa.Column("planner_invocation_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["runtime_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runtime_plan_revisions_plan_id", "runtime_plan_revisions", ["plan_id"])

    op.create_table(
        "runtime_task_attempts",
        sa.Column("id", _uuid(), nullable=False),
        sa.Column("task_row_id", _uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("error", _json(), nullable=True),
        sa.Column("agent_run_id", _uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_row_id"], ["runtime_plan_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_row_id", "attempt_number", name="uq_runtime_task_attempt"),
    )
    op.create_index("ix_runtime_task_attempts_task_row_id", "runtime_task_attempts", ["task_row_id"])
    op.create_index("ix_runtime_task_attempts_status", "runtime_task_attempts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_runtime_task_attempts_status", table_name="runtime_task_attempts")
    op.drop_index("ix_runtime_task_attempts_task_row_id", table_name="runtime_task_attempts")
    op.drop_table("runtime_task_attempts")
    op.drop_index("ix_runtime_plan_revisions_plan_id", table_name="runtime_plan_revisions")
    op.drop_table("runtime_plan_revisions")
    op.drop_index("ix_runtime_task_requirements_status", table_name="runtime_task_requirements")
    op.drop_table("runtime_task_requirements")
    op.drop_table("runtime_task_dependencies")
    op.drop_index("ix_runtime_plan_tasks_ready", table_name="runtime_plan_tasks")
    op.drop_index("uq_runtime_plan_one_running", table_name="runtime_plan_tasks")
    op.drop_table("runtime_plan_tasks")
    op.drop_index("ix_runtime_plans_status", table_name="runtime_plans")
    op.drop_index("ix_runtime_plans_root_run_id", table_name="runtime_plans")
    op.drop_index("ix_runtime_plans_chat_id", table_name="runtime_plans")
    op.drop_index("ix_runtime_plans_tenant_id", table_name="runtime_plans")
    op.drop_table("runtime_plans")
