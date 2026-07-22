"""enforce one running task per plan

Revision ID: 0057
Revises: 0056
"""

from alembic import op
import sqlalchemy as sa


revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_runtime_plan_one_running",
        "runtime_plan_tasks",
        ["plan_id"],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )


def downgrade() -> None:
    op.drop_index("uq_runtime_plan_one_running", table_name="runtime_plan_tasks")

