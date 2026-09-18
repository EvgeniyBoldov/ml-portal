"""Make fresh retrieval an explicit published agent capability.

Revision ID: 0145
Revises: 0144
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0145"
down_revision = "0144"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_versions",
        sa.Column(
            "requires_fresh_retrieval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    # Preserve the current safety posture once, while moving the policy out
    # of runtime code. Future versions configure the capability explicitly.
    op.execute(sa.text("""
        UPDATE agent_versions AS version
        SET requires_fresh_retrieval = true
        FROM agents AS agent
        WHERE agent.id = version.agent_id
          AND COALESCE(agent.tags, ARRAY[]::varchar[]) && ARRAY['jira', 'dcbox', 'backup', 'base_agent']::varchar[]
    """))


def downgrade() -> None:
    op.drop_column("agent_versions", "requires_fresh_retrieval")
