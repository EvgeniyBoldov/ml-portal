"""Align the bootstrap extractor role with glossary candidates.

Revision ID: 0090
Revises: 0089
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = :rules, updated_at = now()
        WHERE role_type = 'fact_extractor'
          AND COALESCE(is_active, true) = true
          AND rules = :previous_rules
    """), {
        "previous_rules": "Используй только user_message, evidence и known_facts. Не используй summary агентов как доказательство. Возвращай только подтверждённые user или tenant факты и аббревиатуры; project facts не извлекай. Не дублируй known_facts и не возвращай больше 8 фактов.",
        "rules": "Используй только user_message, evidence и known_facts. Не используй summary агентов как доказательство. Для терминов и аббревиатур возвращай kind=glossary: subject — канонический термин, value — короткое определение, aliases — явно встречающиеся варианты. Glossary допускается только в user или tenant scope; global и project glossary не извлекай. Каждый кандидат обязан ссылаться на evidence_source_ids. Не дублируй known_facts и не возвращай больше 8 фактов.",
    })


def downgrade() -> None:
    # Never overwrite administrator-edited system roles.
    pass
