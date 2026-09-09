"""Tell the planner to model nullable source fields in task contracts.

Revision ID: 0109
Revises: 0108
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None


_RULE = (
    " Если значение во внешнем источнике может отсутствовать (например, Jira "
    "description), в JSON Schema expected_output явно разрешай null через "
    "тип [\"string\", \"null\"] или соответствующий anyOf; не объявляй такое "
    "поле обязательной строкой."
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE system_llm_roles
            SET rules = rules || :suffix,
                updated_at = now()
            WHERE role_type = 'planner'
              AND COALESCE(is_active, true) = true
              AND rules IS NOT NULL
              AND rules NOT LIKE '%' || :marker || '%'
            """
        ),
        {"suffix": _RULE, "marker": "соответствующий anyOf"},
    )


def downgrade() -> None:
    raise RuntimeError("runtime role prompt alignment migration is irreversible")
