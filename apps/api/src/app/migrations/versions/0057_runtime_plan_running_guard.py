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
    # 0055 already creates this index as part of the canonical runtime-plan
    # graph.  Keep this follow-up revision idempotent for databases that have
    # already applied 0055, while still repairing installations where the
    # index is missing.
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_runtime_plan_one_running "
        "ON runtime_plan_tasks (plan_id) "
        "WHERE status = 'running'"
    ))


def downgrade() -> None:
    # The index is owned by 0055; do not remove it when only 0057 is
    # downgraded.
    pass
