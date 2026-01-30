"""Collection extended metadata and tool instance link

Revision ID: 0049
Revises: 0048
Create Date: 2025-01-29

Adds:
- primary_key_field, time_column for query configuration
- default_sort for default ordering
- entity_type for LLM context
- guardrails: allow_unfiltered_search, max_limit, query_timeout_seconds
- tool_instance_id FK for auto-created ToolInstance
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to collections table
    op.add_column(
        "collections",
        sa.Column("primary_key_field", sa.String(100), nullable=False, server_default="id")
    )
    op.add_column(
        "collections",
        sa.Column("time_column", sa.String(100), nullable=True)
    )
    op.add_column(
        "collections",
        sa.Column("default_sort", JSONB, nullable=True)
    )
    op.add_column(
        "collections",
        sa.Column("entity_type", sa.String(100), nullable=True)
    )
    op.add_column(
        "collections",
        sa.Column("allow_unfiltered_search", sa.Boolean, nullable=False, server_default="false")
    )
    op.add_column(
        "collections",
        sa.Column("max_limit", sa.Integer, nullable=False, server_default="100")
    )
    op.add_column(
        "collections",
        sa.Column("query_timeout_seconds", sa.Integer, nullable=False, server_default="10")
    )
    op.add_column(
        "collections",
        sa.Column(
            "tool_instance_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tool_instances.id", ondelete="SET NULL"),
            nullable=True
        )
    )
    
    # Create index on tool_instance_id
    op.create_index(
        "ix_collections_tool_instance_id",
        "collections",
        ["tool_instance_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_collections_tool_instance_id", table_name="collections")
    op.drop_column("collections", "tool_instance_id")
    op.drop_column("collections", "query_timeout_seconds")
    op.drop_column("collections", "max_limit")
    op.drop_column("collections", "allow_unfiltered_search")
    op.drop_column("collections", "entity_type")
    op.drop_column("collections", "default_sort")
    op.drop_column("collections", "time_column")
    op.drop_column("collections", "primary_key_field")
