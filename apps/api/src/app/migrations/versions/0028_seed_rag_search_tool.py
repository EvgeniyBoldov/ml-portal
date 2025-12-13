"""Seed rag.search tool for Agent Runtime

Revision ID: 0028_seed_rag_search_tool
Revises: 0027_add_celery_task_id
Create Date: 2025-12-13

"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy.dialects import postgresql

revision: str = '0028_seed_rag_search_tool'
down_revision: Union[str, None] = '0027_add_celery_task_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    tools_table = table('tools',
        column('id', postgresql.UUID(as_uuid=True)),
        column('slug', sa.String),
        column('name', sa.String),
        column('description', sa.Text),
        column('type', sa.String),
        column('input_schema', postgresql.JSONB),
        column('output_schema', postgresql.JSONB),
        column('config', postgresql.JSONB),
        column('is_active', sa.Boolean),
        column('created_at', sa.DateTime),
        column('updated_at', sa.DateTime)
    )

    now = datetime.utcnow()

    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to find relevant documents"
            },
            "k": {
                "type": "integer",
                "description": "Number of results to return (default: 5, max: 20)",
                "default": 5,
                "minimum": 1,
                "maximum": 20
            },
            "scope": {
                "type": "string",
                "description": "Search scope: 'tenant' (only tenant docs), 'global' (shared docs), 'all' (both)",
                "enum": ["tenant", "global", "all"],
                "default": "tenant"
            }
        },
        "required": ["query"]
    }

    output_schema = {
        "type": "object",
        "properties": {
            "hits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "source_id": {"type": "string"},
                        "page": {"type": "integer"},
                        "score": {"type": "number"}
                    }
                }
            },
            "total": {"type": "integer"}
        }
    }

    op.bulk_insert(tools_table, [
        {
            'id': uuid.uuid4(),
            'slug': 'rag.search',
            'name': 'Knowledge Base Search',
            'description': (
                'Search the company knowledge base for relevant information. '
                'Use this tool when you need to find documentation, policies, '
                'technical guides, or any other stored knowledge.'
            ),
            'type': 'builtin',
            'input_schema': input_schema,
            'output_schema': output_schema,
            'config': {
                'handler': 'app.agents.builtins.rag_search.RagSearchTool',
                'builtin': True
            },
            'is_active': True,
            'created_at': now,
            'updated_at': now
        }
    ])


def downgrade() -> None:
    op.execute("DELETE FROM tools WHERE slug = 'rag.search'")
