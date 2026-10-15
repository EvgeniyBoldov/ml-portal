"""Align the active TurnPreflight role with the single memory routing policy.

Revision ID: 0190
Revises: 0189
"""
from alembic import op
import sqlalchemy as sa

from app.services.turn_preflight_prompt_v3 import TURN_PREFLIGHT_PROMPT_V3

revision = "0190"
down_revision = "0189"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep model and execution settings operator-owned while removing stale,
    # contradictory prompt text from the active production role.
    op.execute(sa.text("""UPDATE system_llm_roles SET
        identity = :identity, mission = :mission, rules = :rules,
        safety = :safety, output_requirements = :output_requirements,
        examples = '[]'::jsonb, updated_at = now()
        WHERE role_type = 'turn_preflight' AND is_active IS TRUE
    """).bindparams(**TURN_PREFLIGHT_PROMPT_V3))


def downgrade() -> None:
    # Prompt changes remain operator configuration; older text is not restored.
    pass
