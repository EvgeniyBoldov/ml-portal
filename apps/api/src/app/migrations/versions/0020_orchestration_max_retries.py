"""Add executor_max_retries to orchestration_settings.

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-06
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orchestration_settings",
        sa.Column(
            "executor_max_retries",
            sa.Integer(),
            nullable=True,
            comment="Default max tool call retries per step",
        ),
    )


def downgrade() -> None:
    op.drop_column("orchestration_settings", "executor_max_retries")
