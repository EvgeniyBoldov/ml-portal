"""Seed collection tools in database

Revision ID: 0050
Revises: 0049
Create Date: 2025-01-29

Seeds:
- collection.get tool
- collection.aggregate tool
(collection.search already exists)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid


revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    
    # Get collection tool group ID
    result = conn.execute(
        sa.text("SELECT id FROM tool_groups WHERE slug = 'collection'")
    )
    row = result.fetchone()
    
    if not row:
        # Create collection tool group if it doesn't exist
        collection_group_id = uuid.uuid4()
        conn.execute(
            sa.text("""
                INSERT INTO tool_groups (id, slug, name, description, created_at, updated_at)
                VALUES (:id, 'collection', 'Collections', 'Tools for working with data collections', NOW(), NOW())
            """),
            {"id": collection_group_id}
        )
    else:
        collection_group_id = row[0]
    
    # Seed collection.get tool
    conn.execute(
        sa.text("""
            INSERT INTO tools (id, slug, tool_group_id, name, description, type, input_schema, output_schema, config, is_active, created_at, updated_at)
            VALUES (
                :id,
                'collection.get',
                :tool_group_id,
                'Collection Get',
                'Get a single record from a collection by its primary key',
                'database',
                :input_schema,
                :output_schema,
                '{}',
                true,
                NOW(),
                NOW()
            )
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                input_schema = EXCLUDED.input_schema,
                output_schema = EXCLUDED.output_schema,
                updated_at = NOW()
        """),
        {
            "id": uuid.uuid4(),
            "tool_group_id": collection_group_id,
            "input_schema": """{
                "type": "object",
                "properties": {
                    "collection_slug": {"type": "string", "description": "The collection to get record from"},
                    "id": {"type": "string", "description": "The primary key value"},
                    "id_field": {"type": "string", "description": "Primary key field name (optional)"}
                },
                "required": ["collection_slug", "id"]
            }""",
            "output_schema": """{
                "type": "object",
                "properties": {
                    "record": {"type": "object"},
                    "found": {"type": "boolean"},
                    "collection": {"type": "string"}
                }
            }"""
        }
    )
    
    # Seed collection.aggregate tool
    conn.execute(
        sa.text("""
            INSERT INTO tools (id, slug, tool_group_id, name, description, type, input_schema, output_schema, config, is_active, created_at, updated_at)
            VALUES (
                :id,
                'collection.aggregate',
                :tool_group_id,
                'Collection Aggregate',
                'Get aggregated statistics from a collection (count, sum, avg, etc.)',
                'database',
                :input_schema,
                :output_schema,
                '{}',
                true,
                NOW(),
                NOW()
            )
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                input_schema = EXCLUDED.input_schema,
                output_schema = EXCLUDED.output_schema,
                updated_at = NOW()
        """),
        {
            "id": uuid.uuid4(),
            "tool_group_id": collection_group_id,
            "input_schema": """{
                "type": "object",
                "properties": {
                    "collection_slug": {"type": "string", "description": "The collection to aggregate"},
                    "metrics": {
                        "type": "array",
                        "description": "List of metrics (count, sum, avg, min, max, count_distinct)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "function": {"type": "string", "enum": ["count", "count_distinct", "sum", "avg", "min", "max"]},
                                "field": {"type": "string"},
                                "alias": {"type": "string"}
                            }
                        }
                    },
                    "group_by": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
                    "filters": {"type": "object", "description": "Filter conditions"}
                },
                "required": ["collection_slug", "metrics"]
            }""",
            "output_schema": """{
                "type": "object",
                "properties": {
                    "results": {"type": "array", "items": {"type": "object"}},
                    "total_groups": {"type": "integer"},
                    "collection": {"type": "string"}
                }
            }"""
        }
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM tools WHERE slug IN ('collection.get', 'collection.aggregate')"))
