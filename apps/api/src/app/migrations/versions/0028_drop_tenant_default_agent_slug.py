"""Drop legacy tenant.default_agent_slug column.

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("tenants", "default_agent_slug")


def downgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "default_agent_slug",
            sa.String(length=100),
            nullable=True,
            comment="Default agent slug for this tenant",
        ),
    )
