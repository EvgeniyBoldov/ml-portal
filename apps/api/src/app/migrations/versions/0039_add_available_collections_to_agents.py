"""Add available_collections field to agents table

Revision ID: 0039_add_available_collections_to_agents
Revises: 0038_seed_collections_agent
Create Date: 2026-01-21

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0039_add_available_collections_to_agents'
down_revision: Union[str, None] = '0038_seed_collections_agent'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add available_collections field to agents table.
    This field stores a list of collection slugs that the agent can access
    when using the collection.search tool.
    """
    op.add_column(
        'agents',
        sa.Column(
            'available_collections',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default='[]'
        )
    )


def downgrade() -> None:
    """Remove available_collections field from agents table."""
    op.drop_column('agents', 'available_collections')
