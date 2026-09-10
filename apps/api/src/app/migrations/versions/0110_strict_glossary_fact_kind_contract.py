"""Make the fact-extractor glossary routing contract explicit.

Revision ID: 0110
Revises: 0109
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0110"
down_revision = "0109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = :rules, updated_at = now()
        WHERE role_type = 'fact_extractor'
          AND COALESCE(is_active, true) = true
    """), {
        "rules": (
            "Источником может быть только user_message или первичный успешный результат tool "
            "из evidence; summaries агентов, planner и synthesizer доказательствами не являются. "
            "Не дублируй known_facts, не извлекай временные намерения, ход разговора, ошибки "
            "runtime или неподтверждённые предположения. Используй scope=user для пользователя "
            "и scope=tenant для общего рабочего стандарта. scope=project не возвращай. "
            "Поле kind — маршрут хранения: используй только kind=fact или kind=glossary. "
            "Каждый явно определённый термин или аббревиатура, включая элементы переданного "
            "глоссария, обязан иметь kind=glossary; subject — канонический термин, value — "
            "краткое определение, aliases — только явно указанные варианты. Никогда не возвращай "
            "kind=definition, term или другие значения. Для glossary используй только scope=user "
            "или tenant. Каждый факт обязан содержать evidence_source_ids из входного evidence. "
            "Не более 8 фактов; subject и value должны быть короткими и нормализованными."
        ),
    })


def downgrade() -> None:
    raise RuntimeError("runtime role prompt alignment migration is irreversible")
