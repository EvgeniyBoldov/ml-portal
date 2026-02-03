"""Add tool_backend_releases and tool_releases tables

Revision ID: 0058
Revises: 0057
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0058'
down_revision: Union[str, None] = '0057'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create tool_backend_releases table
    op.create_table(
        'tool_backend_releases',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tool_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tools.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('version', sa.String(50), nullable=False),
        sa.Column('input_schema', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('output_schema', postgresql.JSONB(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('method_name', sa.String(100), nullable=False),
        sa.Column('deprecated', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('deprecation_message', sa.Text(), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tool_id', 'version', name='uq_tool_backend_release_version'),
    )
    
    # Create tool_releases table
    op.create_table(
        'tool_releases',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('tool_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tools.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('backend_release_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tool_backend_releases.id', ondelete='RESTRICT'), nullable=False, index=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft', index=True),
        sa.Column('config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint('tool_id', 'version', name='uq_tool_release_version'),
    )
    
    # Add recommended_release_id to tools table
    op.add_column(
        'tools',
        sa.Column('recommended_release_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    
    # Add foreign key constraint for recommended_release_id
    op.create_foreign_key(
        'fk_tools_recommended_release',
        'tools',
        'tool_releases',
        ['recommended_release_id'],
        ['id'],
        ondelete='SET NULL'
    )
    
    # Create index for recommended_release_id
    op.create_index('ix_tools_recommended_release_id', 'tools', ['recommended_release_id'])


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_tools_recommended_release_id', table_name='tools')
    
    # Drop foreign key constraint
    op.drop_constraint('fk_tools_recommended_release', 'tools', type_='foreignkey')
    
    # Drop recommended_release_id column
    op.drop_column('tools', 'recommended_release_id')
    
    # Drop tool_releases table
    op.drop_table('tool_releases')
    
    # Drop tool_backend_releases table
    op.drop_table('tool_backend_releases')
