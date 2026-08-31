"""Add execution kind for runtime plan nodes.

Revision ID: 0092
Revises: 0091
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runtime_plan_tasks",
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="agent"),
    )
    op.alter_column("runtime_plan_tasks", "executor", existing_type=sa.String(length=255), nullable=True)


def downgrade() -> None:
    # Planner checkpoints have no valid representation in the legacy schema.
    # Do not destroy persisted plan history to emulate a downgrade.
    pass
