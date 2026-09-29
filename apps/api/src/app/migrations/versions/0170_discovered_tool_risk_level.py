"""Store risk level on discovered tools.

Revision ID: 0170
Revises: 0169
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0170"
down_revision = "0169"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discovered_tools",
        sa.Column("risk_level", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("discovered_tools", "risk_level")
