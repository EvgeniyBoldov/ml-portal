"""
Create baselines table and baseline_versions table.
Baseline is a separate entity from Prompt for managing restrictions and rules.

Revision ID: 0054
Revises: 0053
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0054'
down_revision = '0053'
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


def downgrade() -> None:
    # Drop tables
    op.drop_table('baseline_versions')
    op.drop_table('baselines')
