"""Persist the semantic-memory selector contract.

Revision ID: 0120
Revises: 0119
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0120"
down_revision = "0119"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET mission = 'Отбери проверяемый контекст из долговременной памяти, каталога проектов и доступного glossary для текущего запроса.',
            rules = 'Используй только индексы facts, projects, glossary и semantic_memory из входного JSON. semantic_memory уже прошла ACL и hybrid retrieval; выбирай её по смыслу, не требуя буквального совпадения слов. Не добавляй факты и не строй план. Выбирай не более 12 фактов, 3 проектов, 6 терминов и 12 memory items.',
            output_requirements = 'Верни JSON с fact_indexes, project_indexes, glossary_indexes, memory_indexes, ambiguities и intent (informational, action или unknown). Каждый индекс обязан существовать в соответствующем входном списке.',
            updated_at = now()
        WHERE role_type = 'memory'
    """))


def downgrade() -> None:
    pass
