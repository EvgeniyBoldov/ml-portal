"""Use the canonical graph task vocabulary.

This is a schema-only rename: persisted runtime plans retain their values
while all runtime surfaces move to executor/intent/instructions/needs.
"""
from alembic import op


revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("runtime_plan_tasks", "agent_slug", new_column_name="executor")
    op.alter_column("runtime_plan_tasks", "title", new_column_name="intent")
    op.alter_column("runtime_plan_tasks", "objective", new_column_name="instructions")
    op.rename_table("runtime_task_requirements", "runtime_task_needs")
    op.alter_column("runtime_task_needs", "requirement_key", new_column_name="need_key")
    op.drop_constraint("uq_runtime_task_requirement", "runtime_task_needs", type_="unique")
    op.create_unique_constraint("uq_runtime_task_need", "runtime_task_needs", ["task_row_id", "need_key"])
    op.drop_index("ix_runtime_task_requirements_status", table_name="runtime_task_needs")
    op.create_index("ix_runtime_task_needs_status", "runtime_task_needs", ["status"])


def downgrade() -> None:
    raise RuntimeError("runtime graph vocabulary is irreversible")
