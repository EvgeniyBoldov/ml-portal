"""Align default memory roles with global glossary candidates.

Revision ID: 0091
Revises: 0090
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("""
        UPDATE system_llm_roles
        SET mission = :mission, rules = :rules,
            output_requirements = :output_requirements, updated_at = now()
        WHERE role_type = 'memory'
          AND COALESCE(is_active, true) = true
          AND rules = :previous_rules
    """), {
        "previous_rules": "Используй только индексы facts и projects из входного JSON. Не добавляй факты и не строй план. Выбирай не более 12 фактов и 3 проектов; при отсутствии совпадений верни пустые массивы.",
        "mission": "Отбери проверяемый контекст из долговременной памяти, каталога проектов и global glossary для текущего запроса.",
        "rules": "Используй только индексы facts, projects и glossary из входного JSON. Не добавляй факты и не строй план. Выбирай не более 12 фактов, 3 проектов и 6 терминов; при отсутствии совпадений верни пустые массивы.",
        "output_requirements": "Верни JSON с fact_indexes, project_indexes, glossary_indexes и ambiguities. Каждый индекс обязан существовать во входе.",
    })
    conn.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = :rules, updated_at = now()
        WHERE role_type = 'fact_extractor'
          AND COALESCE(is_active, true) = true
          AND rules = :previous_rules
    """), {
        "previous_rules": "Используй только user_message, evidence и known_facts. Не используй summary агентов как доказательство. Для терминов и аббревиатур возвращай kind=glossary: subject — канонический термин, value — короткое определение, aliases — явно встречающиеся варианты. Glossary допускается только в user или tenant scope; global и project glossary не извлекай. Каждый кандидат обязан ссылаться на evidence_source_ids. Не дублируй known_facts и не возвращай больше 8 фактов.",
        "rules": "Используй только user_message, evidence и known_facts. Не используй summary агентов как доказательство. Для терминов и аббревиатур возвращай kind=glossary: subject — канонический термин, value — короткое определение, aliases — явно встречающиеся варианты. Для терминов, подтверждённых evidence успешного collection.document.search или collection.table.search, используй tenant scope: runtime сохранит их как global glossary-кандидаты. Project glossary не извлекай. Каждый кандидат обязан ссылаться на evidence_source_ids. Не дублируй known_facts и не возвращай больше 8 фактов.",
    })


def downgrade() -> None:
    # Do not overwrite administrator-edited system-role prompts.
    pass
