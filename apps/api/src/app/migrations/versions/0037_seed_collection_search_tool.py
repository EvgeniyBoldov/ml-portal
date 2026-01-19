"""Seed collection.search tool for Agent Runtime

Revision ID: 0037_seed_collection_search_tool
Revises: 0036_create_collections_table
Create Date: 2026-01-19

"""
from typing import Sequence, Union
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from sqlalchemy.dialects import postgresql

revision: str = '0037_seed_collection_search_tool'
down_revision: Union[str, None] = '0036_create_collections_table'
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
            "collection_slug": {
                "type": "string",
                "description": "The collection to search in"
            },
            "query": {
                "type": "string",
                "description": "Search query (searches in text fields with LIKE)"
            },
            "filters": {
                "type": "object",
                "description": "Field-specific filters",
                "additionalProperties": True
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 50)",
                "default": 50,
                "minimum": 1,
                "maximum": 100
            }
        },
        "required": ["collection_slug"]
    }

    output_schema = {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {"type": "object"}
            },
            "total": {"type": "integer"},
            "collection": {"type": "string"}
        }
    }

    op.bulk_insert(tools_table, [
        {
            'id': uuid.uuid4(),
            'slug': 'collection.search',
            'name': 'Collection Search',
            'description': (
                'Search in a dynamic data collection. '
                'Use this tool to query structured data like tickets, inventory, logs. '
                'Supports text search (LIKE), exact match, and range filters.'
            ),
            'type': 'builtin',
            'input_schema': input_schema,
            'output_schema': output_schema,
            'config': {
                'handler': 'app.agents.builtins.collection_search.CollectionSearchTool',
                'builtin': True
            },
            'is_active': True,
            'created_at': now,
            'updated_at': now
        }
    ])


def downgrade() -> None:
    op.execute("DELETE FROM tools WHERE slug = 'collection.search'")
