"""Persist normalized runtime task-attempt results.

Revision ID: 0096
Revises: 0095
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runtime_task_attempts",
        sa.Column("execution_result", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runtime_task_attempts", "execution_result")
