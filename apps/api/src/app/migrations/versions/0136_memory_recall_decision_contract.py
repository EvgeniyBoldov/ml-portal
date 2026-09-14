"""Persist the explicit Recall grounding decision.

Revision ID: 0136
Revises: 0135
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0136"
down_revision = "0135"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = 'Используй только индексы facts, projects, glossary и semantic_memory из входного JSON. semantic_memory уже прошла ACL и hybrid retrieval; выбирай её по смыслу, не требуя буквального совпадения слов. Не добавляй факты и не строй план. Выбери knowledge_need: none для общего запроса без корпоративного знания, durable для вопроса о компании/проекте/регламенте, current для текущего состояния внешней системы. Выбирай не более 12 фактов, 3 проектов, 6 терминов и 12 memory items.',
            output_requirements = 'Верни JSON с fact_indexes, project_indexes, glossary_indexes, memory_indexes, ambiguities, intent (informational, action или unknown) и knowledge_need (none, durable или current). Каждый индекс обязан существовать во входе.',
            updated_at = now()
        WHERE role_type = 'memory' AND COALESCE(is_active, true)
    """))


def downgrade() -> None:
    pass
