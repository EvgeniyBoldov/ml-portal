"""Seed default agents and add chat system prompt

Revision ID: 0026_seed_default_agents
Revises: 0025_rename_agent_config
Create Date: 2025-12-11

"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0026_seed_default_agents'
down_revision: Union[str, None] = '0025_rename_agent_config'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Define table structures for inserts
    prompts_table = table('prompts',
        column('id', postgresql.UUID(as_uuid=True)),
        column('slug', sa.String),
        column('name', sa.String),
        column('description', sa.Text),
        column('template', sa.Text),
        column('input_variables', postgresql.JSONB),
        column('generation_config', postgresql.JSONB),
        column('version', sa.Integer),
        column('is_active', sa.Boolean),
        column('type', sa.String),
        column('created_at', sa.DateTime),
        column('updated_at', sa.DateTime)
    )

    agents_table = table('agents',
        column('id', postgresql.UUID(as_uuid=True)),
        column('slug', sa.String),
        column('name', sa.String),
        column('description', sa.Text),
        column('system_prompt_slug', sa.String),
        column('tools', postgresql.JSONB),
        column('generation_config', postgresql.JSONB),
        column('is_active', sa.Boolean),
        column('created_at', sa.DateTime),
        column('updated_at', sa.DateTime)
    )

    # 1. Add chat.system prompt (for simple chat without RAG)
    chat_system_template = """Ты — полезный AI-ассистент. Отвечай на вопросы пользователя чётко и по существу.

Правила:
- Отвечай на русском языке, если пользователь пишет на русском
- Будь вежлив и профессионален
- Если не знаешь ответа — честно скажи об этом
- Форматируй ответы с использованием Markdown для лучшей читаемости
"""

    # 2. Add agent.rag.system prompt (full system prompt for RAG agent)
    rag_system_template = """Ты — AI-ассистент с доступом к базе знаний компании. Твоя задача — отвечать на вопросы, используя предоставленный контекст.

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

    now = datetime.utcnow()

    # Insert prompts
    op.bulk_insert(prompts_table, [
        {
            'id': uuid.uuid4(),
            'slug': 'chat.system',
            'name': 'Chat System Prompt',
            'description': 'Базовый системный промпт для чата без RAG.',
            'template': chat_system_template,
            'input_variables': [],
            'generation_config': {},
            'version': 1,
            'is_active': True,
            'type': 'agent',
            'created_at': now,
            'updated_at': now
        },
        {
            'id': uuid.uuid4(),
            'slug': 'agent.rag.system',
            'name': 'RAG Agent System Prompt',
            'description': 'Системный промпт для агента с RAG. Включает инструкции по работе с контекстом.',
            'template': rag_system_template,
            'input_variables': ['rag_context'],
            'generation_config': {},
            'version': 1,
            'is_active': True,
            'type': 'agent',
            'created_at': now,
            'updated_at': now
        }
    ])

    # Insert default agents
    op.bulk_insert(agents_table, [
        {
            'id': uuid.uuid4(),
            'slug': 'chat-simple',
            'name': 'Simple Chat',
            'description': 'Базовый чат-бот без доступа к базе знаний.',
            'system_prompt_slug': 'chat.system',
            'tools': [],
            'generation_config': {},
            'is_active': True,
            'created_at': now,
            'updated_at': now
        },
        {
            'id': uuid.uuid4(),
            'slug': 'chat-rag',
            'name': 'RAG Chat',
            'description': 'Чат-бот с доступом к базе знаний компании (RAG).',
            'system_prompt_slug': 'agent.rag.system',
            'tools': ['rag.search'],
            'generation_config': {},
            'is_active': True,
            'created_at': now,
            'updated_at': now
        }
    ])


def downgrade() -> None:
    op.execute("DELETE FROM agents WHERE slug IN ('chat-simple', 'chat-rag')")
    op.execute("DELETE FROM prompts WHERE slug IN ('chat.system', 'agent.rag.system')")
