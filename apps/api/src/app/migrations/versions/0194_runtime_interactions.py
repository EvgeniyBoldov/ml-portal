"""Allow task-local user interactions with typed answers."""
from alembic import op

revision = "0194"
down_revision = "0193"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_runtime_task_status", "runtime_plan_tasks", type_="check")
    op.create_check_constraint("ck_runtime_task_status", "runtime_plan_tasks",
        "status IN ('pending', 'running', 'waiting_retry', 'waiting_input', 'waiting_confirmation', 'completed', 'needs_dependency', 'unfulfillable', 'failed', 'blocked', 'cancelled')")


def downgrade() -> None:
    op.execute("UPDATE runtime_plan_tasks SET status = 'waiting_confirmation' WHERE status = 'waiting_input'")
    op.drop_constraint("ck_runtime_task_status", "runtime_plan_tasks", type_="check")
    op.create_check_constraint("ck_runtime_task_status", "runtime_plan_tasks",
        "status IN ('pending', 'running', 'waiting_retry', 'waiting_confirmation', 'completed', 'needs_dependency', 'unfulfillable', 'failed', 'blocked', 'cancelled')")
