"""Update RAG agent prompt for tool-call format

The RAG agent now uses rag.search tool via AgentRuntime instead of
direct {{ rag_context }} injection. Update the system prompt accordingly.

Revision ID: 0029_update_rag_agent_prompt
Revises: 0028_seed_rag_search_tool
Create Date: 2025-12-13

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa

revision: str = '0029_update_rag_agent_prompt'
down_revision: Union[str, None] = '0028_seed_rag_search_tool'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# New prompt that works with tool-call loop
NEW_RAG_SYSTEM_TEMPLATE = """Ты — AI-ассистент с доступом к базе знаний компании.

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

# Old prompt for downgrade
OLD_RAG_SYSTEM_TEMPLATE = """Ты — AI-ассистент с доступом к базе знаний компании. Твоя задача — отвечать на вопросы, используя предоставленный контекст.

Правила:
- Отвечай на основе контекста из базы знаний
- Если информации в контексте недостаточно — честно скажи об этом
- При цитировании указывай источник (документ и страницу)
- Отвечай на русском языке
- Форматируй ответы с использованием Markdown

{% if rag_context %}
{{ rag_context }}
{% endif %}
"""


def upgrade() -> None:
    now = datetime.utcnow()
    
    # Update the agent.rag.system prompt
    op.execute(
        sa.text("""
            UPDATE prompts 
            SET template = :template,
                input_variables = :input_vars,
                updated_at = :updated_at
            WHERE slug = 'agent.rag.system'
        """).bindparams(
            template=NEW_RAG_SYSTEM_TEMPLATE,
            input_vars='[]',  # No more rag_context variable
            updated_at=now
        )
    )


def downgrade() -> None:
    now = datetime.utcnow()
    
    # Restore old prompt
    op.execute(
        sa.text("""
            UPDATE prompts 
            SET template = :template,
                input_variables = :input_vars,
                updated_at = :updated_at
            WHERE slug = 'agent.rag.system'
        """).bindparams(
            template=OLD_RAG_SYSTEM_TEMPLATE,
            input_vars='["rag_context"]',
            updated_at=now
        )
    )
