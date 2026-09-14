"""Retire the agent-facing project-memory marker contract.

Revision ID: 0116
Revises: 0115
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0116"
down_revision = "0115"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing published prompts are persisted independently from the seed
    # defaults. Remove marker instructions there as well, otherwise a restart
    # could keep advertising a retired write path.
    op.execute(sa.text("""
        UPDATE agent_versions
        SET rules = regexp_replace(
                COALESCE(rules, ''),
                E'\\n?[^\\n]*memory\\.mark[^\\n]*',
                '', 'gi'
            ),
            tool_use_rules = regexp_replace(
                COALESCE(tool_use_rules, ''),
                E'\\n?[^\\n]*memory\\.mark[^\\n]*',
                '', 'gi'
            ),
            updated_at = now()
        WHERE COALESCE(rules, '') ILIKE '%memory.mark%'
           OR COALESCE(tool_use_rules, '') ILIKE '%memory.mark%'
    """))


def downgrade() -> None:
    # Prompt text is intentionally not reconstructed.
    pass
