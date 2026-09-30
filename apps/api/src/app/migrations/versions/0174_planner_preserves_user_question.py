"""Require planner to preserve the original user question in synthesis briefs.

Revision ID: 0174
Revises: 0173
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0174"
down_revision = "0173"
branch_labels = None
depends_on = None


RULE = (
    "В synthesis_brief.user_question дословно копируй исходный goal из входа, "
    "включая язык и формулировку; не пересказывай его и не меняй пунктуацию. "
    "Это исходный вопрос пользователя, а не краткое описание задачи."
)


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = concat_ws(E'\\n', NULLIF(rules, ''), :rule), updated_at = now()
        WHERE role_type = 'planner' AND COALESCE(is_active, true)
          AND position(:rule in COALESCE(rules, '')) = 0
    """).bindparams(rule=RULE))


def downgrade() -> None:
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = btrim(replace(COALESCE(rules, ''), :rule, '')), updated_at = now()
        WHERE role_type = 'planner' AND COALESCE(is_active, true)
          AND position(:rule in COALESCE(rules, '')) > 0
    """).bindparams(rule=RULE))
