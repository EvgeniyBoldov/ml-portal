"""Align the active TurnPreflight prompt with its routing responsibilities."""

from alembic import op
import sqlalchemy as sa

revision = "0214"
down_revision = "0213"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.turn_preflight_prompt_v3 import TURN_PREFLIGHT_PROMPT_V3

    op.execute(sa.text("""UPDATE system_llm_roles SET
        identity = :identity, mission = :mission, rules = :rules,
        safety = :safety, output_requirements = :output_requirements, updated_at = now()
        WHERE role_type = 'turn_preflight' AND is_active IS TRUE
    """).bindparams(**TURN_PREFLIGHT_PROMPT_V3))


def downgrade() -> None:
    # Do not overwrite the active role configuration with stale prompt text.
    pass
