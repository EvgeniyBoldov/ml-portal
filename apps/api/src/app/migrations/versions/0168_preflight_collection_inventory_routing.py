"""Clarify that mechanical lookup is not a collection access inventory.

Revision ID: 0168
Revises: 0167
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0168"
down_revision = "0167"
branch_labels = None
depends_on = None


_RULE = (
    " mechanical_lookup.projects, glossary и entities содержат только совпадения терминов "
    "из запроса; пустые списки не означают отсутствие коллекций, прав доступа или операций. "
    "Если пользователь спрашивает, какие коллекции ему доступны или какими операциями "
    "он может пользоваться, нужны актуальные данные и проверка RBAC: выбирай planner. "
    "Не утверждай наличие или отсутствие доступных коллекций по mechanical_lookup."
)


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = COALESCE(rules, '') || :rule, updated_at = now()
        WHERE role_type = 'turn_preflight'
          AND COALESCE(is_active, true)
          AND COALESCE(rules, '') NOT LIKE '%пустые списки не означают отсутствие коллекций%'
    """).bindparams(rule=_RULE))


def downgrade() -> None:
    # Existing role text may have been edited by an administrator.
    pass
