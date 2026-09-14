"""Align direct synthesis and memory extraction prompts with writeback order.

Revision ID: 0143
Revises: 0142
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0143"
down_revision = "0142"
branch_labels = None
depends_on = None


_PROMPTS = {
    "synthesizer": {
        "rules": "Сохраняй цель, язык и ограничения synthesis_brief. Runtime добавляет SYNTHESIS INPUT MODE: он определяет единственные допустимые источники содержания. В mode=planned используй только completed_task_reports, явно принятые partial outputs, verified sources/artifacts и limitations; план, намерения задач и непроверенные утверждения не являются результатом. В mode=direct отсутствие отчётов задач нормально: используй только direct_answer_draft, synthesis_brief и memory_context; не требуй план или новые данные. memory_candidates — служебные кандидаты writeback, а не подтверждение записи и не основание перечислять или объявлять результаты. Не добавляй фактов, рекомендаций, ссылок, выполненных действий или статусов, которых нет в разрешённых источниках. Если данные неполны, кратко и честно обозначь границу известного.",
    },
    "fact_extractor": {
        "mission": "Извлеки или проверь атомарные факты по единственному набору первичного evidence для будущих обращений.",
        "rules": "Используй только evidence, known_facts и preflight_candidates. evidence — единственный канонический исходный текст; не ожидай отдельного user_message и не требуй его дублирования. preflight_candidates — только подсказки: кандидат допустим лишь при явном подтверждении первичным evidence. Не используй summary агентов, планы, synthesis-текст или предположения как evidence. Возвращай только устойчивые атомарные сведения, не временные намерения, ход выполнения, ошибки или счётчики. scope только user или tenant; kind только fact или glossary. Для терминов и аббревиатур используй glossary: subject — канонический термин, value — краткое определение, aliases — только явно встречающиеся варианты. Каждый evidence_source_ids содержит только существующие source_id из evidence. Не дублируй known_facts, не возвращай больше 12 фактов и верни пустой facts, если подтверждённых фактов нет.",
    },
}


def upgrade() -> None:
    for role_type, fields in _PROMPTS.items():
        assignments = ", ".join(f"{field} = :{field}" for field in fields)
        op.execute(sa.text(f"""
            UPDATE system_llm_roles
            SET {assignments}, updated_at = now()
            WHERE role_type = :role_type
              AND COALESCE(is_active, true)
        """).bindparams(role_type=role_type, **fields))


def downgrade() -> None:
    pass
