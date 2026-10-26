"""Treat root route policy as advisory input to TurnPreflight.

Revision ID: 0205
Revises: 0204
"""
from alembic import op
import sqlalchemy as sa

revision = "0205"
down_revision = "0204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.turn_preflight_prompt_v3 import TURN_PREFLIGHT_PROMPT_V3

    # Preserve the operator-selected model and every role execution setting.
    op.execute(sa.text("""UPDATE system_llm_roles SET
        rules = :rules, updated_at = now()
        WHERE role_type = 'turn_preflight' AND is_active IS TRUE
    """).bindparams(rules=TURN_PREFLIGHT_PROMPT_V3["rules"]))


def downgrade() -> None:
    # Prompt changes are configuration; do not restore stale routing text.
    pass
