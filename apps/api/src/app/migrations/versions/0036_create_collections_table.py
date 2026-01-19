"""Create collections table

Revision ID: 0036_create_collections_table
Revises: 0035_improve_rag_agent_prompt
Create Date: 2026-01-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0036_create_collections_table'
down_revision: Union[str, None] = '0035_improve_rag_agent_prompt'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'collections',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('type', sa.String(length=20), nullable=False, server_default='sql'),
        sa.Column('fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('table_name', sa.String(length=100), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('ix_collections_tenant_id', 'collections', ['tenant_id'])
    op.create_index('ix_collections_tenant_slug', 'collections', ['tenant_id', 'slug'], unique=True)
    op.create_index('ix_collections_is_active', 'collections', ['is_active'])


def downgrade() -> None:
    op.drop_index('ix_collections_is_active', table_name='collections')
    op.drop_index('ix_collections_tenant_slug', table_name='collections')
    op.drop_index('ix_collections_tenant_id', table_name='collections')
    op.drop_table('collections')
