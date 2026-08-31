"""add runtime task freshness policy

Revision ID: 0095
Revises: 0094
"""
from alembic import op
import sqlalchemy as sa

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runtime_plan_tasks",
        sa.Column("freshness_policy", sa.String(length=32), nullable=False, server_default="allow_memory"),
    )


def downgrade() -> None:
    op.drop_column("runtime_plan_tasks", "freshness_policy")
