"""Add the persisted execution order for runtime plan tasks.

RuntimePlanTask has used ``planned_order`` since the graph planner was
introduced, but the original table migration omitted the column.  Existing
tasks retain a deterministic neutral order while newly written plans persist
their planner-assigned order.
"""

from alembic import op


revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE runtime_plan_tasks "
        "ADD COLUMN IF NOT EXISTS planned_order INTEGER NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE runtime_plan_tasks "
        "DROP COLUMN IF EXISTS planned_order"
    )
