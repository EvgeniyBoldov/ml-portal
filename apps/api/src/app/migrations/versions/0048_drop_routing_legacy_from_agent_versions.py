"""Drop legacy routing fields from agent_versions.

Revision ID: 0048
Revises: 0047
Create Date: 2026-06-11

Removes dead triage-era columns: is_routable, routing_keywords,
routing_negative_keywords. Planner routing is now driven by
Agent.provides_keys and Agent.tags.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("agent_versions", "is_routable")
    op.drop_column("agent_versions", "routing_keywords")
    op.drop_column("agent_versions", "routing_negative_keywords")


def downgrade() -> None:
    op.add_column(
        "agent_versions",
        sa.Column(
            "is_routable",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.add_column(
        "agent_versions",
        sa.Column(
            "routing_keywords",
            sa.ARRAY(sa.String()),
            nullable=True,
        ),
    )
    op.add_column(
        "agent_versions",
        sa.Column(
            "routing_negative_keywords",
            sa.ARRAY(sa.String()),
            nullable=True,
        ),
    )
