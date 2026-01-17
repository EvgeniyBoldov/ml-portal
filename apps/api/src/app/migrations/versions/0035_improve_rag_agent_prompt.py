"""Improve RAG agent prompt to avoid unnecessary tool calls

Fix issue where agent returns tool_call even when explaining empty results.
The agent should NOT call tools again if it already has the results.

Revision ID: 0035_improve_rag_agent_prompt
Revises: 0034_create_api_tokens_table
Create Date: 2026-01-17

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision: str = '0035_improve_rag_agent_prompt'
down_revision: Union[str, None] = '0034_create_api_tokens_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Improved prompt with explicit instructions about when NOT to call tools
NEW_RAG_SYSTEM_TEMPLATE = """Ты — AI-ассистент с доступом к базе знаний компании.

## Твоя задача
Отвечать на вопросы пользователя, используя инструмент поиска по базе знаний.

## Правила работы
1. **Используй rag.search** для поиска информации перед ответом
2. **НЕ вызывай инструменты повторно** если ты уже получил результаты поиска
3. Если поиск вернул пустые результаты (hits: []) — сразу сообщи пользователю, что информация не найдена
4. При пустых результатах НЕ предлагай новый tool_call — просто объясни ситуацию и предложи переформулировать вопрос
5. При цитировании указывай источник (документ и страницу)
6. Отвечай на русском языке
7. Форматируй ответы с использованием Markdown

## Важно
- Не выдумывай информацию — используй только данные из базы знаний
- Если поиск не дал результатов, честно скажи об этом
- После получения результатов tool_call — сразу формулируй финальный ответ
- НЕ делай повторные вызовы rag.search с теми же или похожими параметрами
"""

# Old prompt for downgrade
OLD_RAG_SYSTEM_TEMPLATE = """Ты — AI-ассистент с доступом к базе знаний компании.

## Твоя задача
Отвечать на вопросы пользователя, используя инструмент поиска по базе знаний.

## Правила работы
1. **Всегда используй rag.search** для поиска информации перед ответом
2. Если информации в результатах поиска недостаточно — честно скажи об этом
3. При цитировании указывай источник (документ и страницу)
4. Отвечай на русском языке
5. Форматируй ответы с использованием Markdown

## Важно
- Не выдумывай информацию — используй только данные из базы знаний
- Если поиск не дал результатов, сообщи пользователю и предложи переформулировать вопрос
"""


def upgrade() -> None:
    # Update the agent.rag.system prompt
    escaped_template = NEW_RAG_SYSTEM_TEMPLATE.replace("'", "''")
    op.execute(f"""
        UPDATE prompts 
        SET template = '{escaped_template}',
            updated_at = NOW()
        WHERE slug = 'agent.rag.system'
    """)


def downgrade() -> None:
    # Restore old prompt
    escaped_template = OLD_RAG_SYSTEM_TEMPLATE.replace("'", "''")
    op.execute(f"""
        UPDATE prompts 
        SET template = '{escaped_template}',
            updated_at = NOW()
        WHERE slug = 'agent.rag.system'
    """)
