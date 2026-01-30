"""
Create baselines table and baseline_versions table.
Baseline is a separate entity from Prompt for managing restrictions and rules.

Revision ID: 0042
Revises: 0041
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0042'
down_revision = '0041'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create baselines table
    op.create_table(
        'baselines',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slug', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('scope', sa.String(20), nullable=False, default='default', index=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    
    # Create baseline_versions table
    op.create_table(
        'baseline_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('baseline_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('baselines.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('template', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, default='draft', index=True),
        sa.Column('parent_version_id', postgresql.UUID(as_uuid=True), 
                  sa.ForeignKey('baseline_versions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('baseline_id', 'version', name='uix_baseline_version'),
    )
    
    # Rename baseline_prompt_id to baseline_id and change FK
    # First, drop old FK constraint if exists
    try:
        op.drop_constraint('agents_baseline_prompt_id_fkey', 'agents', type_='foreignkey')
    except Exception:
        pass  # Constraint may not exist
    
    # Rename column
    op.alter_column('agents', 'baseline_prompt_id', new_column_name='baseline_id')
    
    # Add new FK constraint to baselines table
    op.create_foreign_key(
        'agents_baseline_id_fkey',
        'agents', 'baselines',
        ['baseline_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Create index on baseline_id
    op.create_index('ix_agents_baseline_id', 'agents', ['baseline_id'])


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_agents_baseline_id', 'agents')
    
    # Drop FK constraint
    op.drop_constraint('agents_baseline_id_fkey', 'agents', type_='foreignkey')
    
    # Rename column back
    op.alter_column('agents', 'baseline_id', new_column_name='baseline_prompt_id')
    
    # Restore old FK constraint to prompts
    op.create_foreign_key(
        'agents_baseline_prompt_id_fkey',
        'agents', 'prompts',
        ['baseline_prompt_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # Drop tables
    op.drop_table('baseline_versions')
    op.drop_table('baselines')
