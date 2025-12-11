"""Seed default prompts

Revision ID: 0021_seed_default_prompts
Revises: 0020_add_prompts_table
Create Date: 2025-11-30

"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0021_seed_default_prompts'
down_revision: Union[str, None] = '0020_add_prompts_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Define the table structure for the insert
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

    # Default RAG System Prompt
    rag_template = """# Контекст из базы знаний

Используй следующую информацию для ответа. При цитировании указывай источник.

{% for result in results %}
## Источник {{ loop.index }}
{{ result.text }}

*Документ: {{ result.source_id }}, страница: {{ result.page or 'N/A' }}*
{% if result.model_hits %}
*Модели: {{ result.model_hits }}*
{% endif %}

---

{% endfor %}
"""

    op.bulk_insert(prompts_table, [
        {
            'id': uuid.uuid4(),
            'slug': 'chat.rag.system',
            'name': 'RAG System Prompt',
            'description': 'Системный промпт для формирования контекста RAG (Retrieval Augmented Generation). Вставляет найденные чанки документов перед вопросом пользователя.',
            'template': rag_template,
            'input_variables': ['results'],
            'generation_config': {},
            'version': 1,
            'is_active': True,
            'type': 'chat',
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
    ])


def downgrade() -> None:
    op.execute("DELETE FROM prompts WHERE slug = 'chat.rag.system'")
