"""Normalize discovered operation policy risk to the platform binary enum.

Revision ID: 0207
Revises: 0206
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0207"
down_revision = "0206"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE discovered_tools
        SET risk_level = CASE lower(trim(risk_level))
            WHEN 'safe' THEN 'safe'
            WHEN 'read_only' THEN 'safe'
            WHEN 'readonly' THEN 'safe'
            WHEN 'risky' THEN 'risky'
            WHEN 'write' THEN 'risky'
            WHEN 'mutable' THEN 'risky'
            WHEN 'mutating' THEN 'risky'
            WHEN 'destructive' THEN 'risky'
            WHEN 'dangerous' THEN 'risky'
            ELSE NULL
        END
        WHERE risk_level IS NOT NULL
        """
    )
    op.create_check_constraint(
        "ck_discovered_tool_policy_risk_level",
        "discovered_tools",
        "risk_level IS NULL OR risk_level IN ('safe', 'risky')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE discovered_tools SET risk_level = 'write' WHERE risk_level = 'risky'"
    )
    op.drop_constraint(
        "ck_discovered_tool_policy_risk_level",
        "discovered_tools",
        type_="check",
    )
