"""add is_default to credentials

Revision ID: 0044
Revises: 0043
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0044'
down_revision = '0043'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_default column (default False)
    op.add_column(
        'credential_sets',
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='false')
    )
    
    # Create unique constraint: only one default per (tool_instance_id, scope, tenant_id, user_id)
    # This ensures user can't have multiple default credentials for same instance
    op.create_index(
        'ix_credential_sets_default_unique',
        'credential_sets',
        ['tool_instance_id', 'scope', 'tenant_id', 'user_id'],
        unique=True,
        postgresql_where=sa.text('is_default = true')
    )


def downgrade():
    op.drop_index('ix_credential_sets_default_unique', table_name='credential_sets')
    op.drop_column('credential_sets', 'is_default')
