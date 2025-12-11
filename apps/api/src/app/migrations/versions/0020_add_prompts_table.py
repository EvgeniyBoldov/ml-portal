"""Add prompts table

Revision ID: 0020_add_prompts_table
Revises: 0019_cleanup_and_rerank
Create Date: 2025-11-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0020_add_prompts_table'
down_revision: Union[str, None] = '0019_cleanup_and_rerank'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('prompts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('template', sa.Text(), nullable=False),
        sa.Column('input_variables', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('generation_config', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('version', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('type', sa.String(length=50), nullable=False, server_default='chat'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prompts_slug'), 'prompts', ['slug'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_prompts_slug'), table_name='prompts')
    op.drop_table('prompts')
