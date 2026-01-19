"""Seed collections agent with collection.search tool

Revision ID: 0038_seed_collections_agent
Revises: 0037_seed_collection_search_tool
Create Date: 2026-01-19

"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy.dialects import postgresql

revision: str = '0038_seed_collections_agent'
down_revision: Union[str, None] = '0037_seed_collection_search_tool'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


COLLECTIONS_AGENT_PROMPT = """Ты — AI-ассистент с доступом к структурированным данным компании.

## Твоя задача
Отвечать на вопросы пользователя, используя инструмент поиска по коллекциям данных.

## Доступные коллекции
- **it_tickets** — IT-тикеты (инциденты, задачи). Поля: number, title, body

## Правила работы
1. Используй collection.search для поиска информации перед ответом
2. НЕ вызывай инструменты повторно если ты уже получил результаты
3. После получения результатов — сразу формулируй финальный ответ
4. При цитировании указывай номер тикета или источник
5. Отвечай на русском языке
6. Если данных нет — честно скажи об этом

## Формат вызова инструмента
Для поиска используй:
- collection_slug: "it_tickets" (или другая коллекция)
- query: поисковый запрос (ищет по текстовым полям)
- filters: дополнительные фильтры по полям
- limit: количество результатов (по умолчанию 50)

## Пример
Пользователь: "Найди тикеты про VLAN"
→ Вызови collection.search с query="VLAN", collection_slug="it_tickets"
→ Получи результаты
→ Сформулируй ответ на основе найденных тикетов
"""


def upgrade() -> None:
    prompts_table = table('prompts',
        column('id', postgresql.UUID(as_uuid=True)),
        column('slug', sa.String),
        column('name', sa.String),
        column('template', sa.Text),
        column('input_variables', postgresql.JSONB),
        column('version', sa.Integer),
        column('is_active', sa.Boolean),
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
        column('enable_logging', sa.Boolean),
        column('created_at', sa.DateTime),
        column('updated_at', sa.DateTime)
    )

    now = datetime.utcnow()

    # 1. Create system prompt for collections agent
    op.bulk_insert(prompts_table, [
        {
            'id': uuid.uuid4(),
            'slug': 'agent.collections.system',
            'name': 'Collections Agent System Prompt',
            'template': COLLECTIONS_AGENT_PROMPT,
            'input_variables': [],
            'version': 1,
            'is_active': True,
            'created_at': now,
            'updated_at': now
        }
    ])

    # 2. Create collections agent
    op.bulk_insert(agents_table, [
        {
            'id': uuid.uuid4(),
            'slug': 'chat-collections',
            'name': 'Data Collections',
            'description': 'Поиск по структурированным данным (тикеты, инвентарь)',
            'system_prompt_slug': 'agent.collections.system',
            'tools': ['collection.search'],
            'generation_config': {
                'temperature': 0.3,
                'max_tokens': 2048
            },
            'is_active': True,
            'enable_logging': True,
            'created_at': now,
            'updated_at': now
        }
    ])


def downgrade() -> None:
    op.execute("DELETE FROM agents WHERE slug = 'chat-collections'")
    op.execute("DELETE FROM prompts WHERE slug = 'agent.collections.system'")
