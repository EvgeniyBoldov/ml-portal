"""Add tool release metadata fields

Revision ID: 0059
Revises: 0058
Create Date: 2025-02-03 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0059'
down_revision = '0058'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to tool_releases
    op.add_column('tool_releases', sa.Column('description_for_llm', sa.Text(), nullable=True))
    op.add_column('tool_releases', sa.Column('category', sa.String(100), nullable=True))
    op.add_column('tool_releases', sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'))
    op.add_column('tool_releases', sa.Column('field_hints', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'))
    op.add_column('tool_releases', sa.Column('examples', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='[]'))
    op.add_column('tool_releases', sa.Column('return_summary', sa.Text(), nullable=True))
    op.add_column('tool_releases', sa.Column('meta_hash', sa.String(64), nullable=True))
    
    # Add new column to tools
    op.add_column('tools', sa.Column('name_for_llm', sa.String(255), nullable=True))


def downgrade() -> None:
    # Remove columns from tools
    op.drop_column('tools', 'name_for_llm')
    
    # Remove columns from tool_releases
    op.drop_column('tool_releases', 'meta_hash')
    op.drop_column('tool_releases', 'return_summary')
    op.drop_column('tool_releases', 'examples')
    op.drop_column('tool_releases', 'field_hints')
    op.drop_column('tool_releases', 'tags')
    op.drop_column('tool_releases', 'category')
    op.drop_column('tool_releases', 'description_for_llm')
