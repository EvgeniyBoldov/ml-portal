"""Remove project-fact fields from persisted LLM role contracts.

Revision ID: 0118
Revises: 0117
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0118"
down_revision = "0117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = 'Используй только user_message, evidence и known_facts. Не используй summary агентов как доказательство. Для терминов и аббревиатур возвращай kind=glossary: subject — канонический термин, value — короткое определение, aliases — явно встречающиеся варианты. Для терминов, подтверждённых evidence успешного collection.document.search или collection.table.search, используй tenant scope: runtime сохранит их как global glossary-кандидаты. Каждый кандидат обязан ссылаться на evidence_source_ids. Не дублируй known_facts и не возвращай больше 8 фактов.',
            output_requirements = 'Верни JSON с facts[]. Каждый факт содержит scope, kind (fact или glossary), subject, value, confidence, aliases и evidence_source_ids.',
            updated_at = now()
        WHERE role_type = 'fact_extractor'
    """))


def downgrade() -> None:
    pass
