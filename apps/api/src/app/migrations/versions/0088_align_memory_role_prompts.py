"""Align default memory role prompts with project candidate compaction.

Revision ID: 0088
Revises: 0087
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Update only the exact historical bootstrap prompt; independently edited
    # administrator prompts remain untouched.
    conn.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = :rules, updated_at = now()
        WHERE role_type = 'fact_extractor'
          AND COALESCE(is_active, true) = true
          AND rules = :previous_rules
    """), {
        "previous_rules": "Вход: user_message, evidence, known_facts. Не используй summary агентов как доказательство. Возвращай только подтверждённые user, tenant или project факты с evidence_source_ids; не дублируй known_facts и не возвращай более 8 фактов.",
        "rules": "Вход: user_message, evidence, known_facts. Не используй summary агентов как доказательство. Возвращай только подтверждённые user или tenant факты и аббревиатуры; project facts не извлекай. Не дублируй known_facts и не возвращай более 8 фактов.",
    })
    conn.execute(sa.text("""
        UPDATE system_llm_roles
        SET mission = :mission, rules = :rules, output_requirements = :output_requirements, updated_at = now()
        WHERE role_type = 'fact_compactor'
          AND COALESCE(is_active, true) = true
          AND rules = :previous_rules
    """), {
        "previous_rules": "Используй только candidates. Объединяй смысловые дубли, не разрешай противоречия и всегда указывай source_candidate_indexes.",
        "mission": "Семантически нормализуй user, tenant, glossary и project-кандидаты без создания новых сведений.",
        "rules": "Используй candidates и current_facts. Для user/tenant объединяй смысловые дубли после точных совпадений. Для glossary нормализуй термин и алиасы. Project-кандидаты всегда компактируй через LLM: сохраняй операционный смысл, объединяй правила и исключения, не выдумывай сведения. Всегда указывай source_candidate_indexes.",
        "output_requirements": "Верни JSON с facts[]. Каждый факт содержит scope, subject, value, action и source_candidate_indexes. action: add | rewrite | merge | supersede | mark_conflict | discard.",
    })


def downgrade() -> None:
    # Do not overwrite administrator-edited prompts during downgrade.
    pass
