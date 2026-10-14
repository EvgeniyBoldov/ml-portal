"""Use registered memory.search in root routing.

Revision ID: 0188
Revises: 0187
"""
from alembic import op
import sqlalchemy as sa

from app.services.turn_preflight_prompt_v3 import TURN_PREFLIGHT_PROMPT_V3

revision = "0188"
down_revision = "0187"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve the configured model, temperature and execution limits.
    op.execute(sa.text("""UPDATE system_llm_roles SET
        identity = :identity, mission = :mission, rules = :rules,
        safety = :safety, output_requirements = :output_requirements,
        examples = '[]'::jsonb, updated_at = now()
        WHERE role_type = 'turn_preflight' AND is_active IS TRUE
    """).bindparams(**TURN_PREFLIGHT_PROMPT_V3))


def downgrade() -> None:
    # Prompt edits remain operator configuration, as in migration 0182.
    pass
