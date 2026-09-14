"""Use the current connector model for TurnPreflight.

Revision ID: 0139
Revises: 0138
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0139"
down_revision = "0138"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Do not overwrite an administrator-selected model. Only repair the
    # legacy bootstrap alias that cannot be resolved by the current connector.
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET model = 'llm.groq.gptoss', updated_at = now()
        WHERE role_type = 'turn_preflight'
          AND model = 'llm.llama4.scout'
    """))


def downgrade() -> None:
    # The previous alias is intentionally not restored: it is not resolvable
    # in the current connector catalog and would make preflight fail again.
    pass
