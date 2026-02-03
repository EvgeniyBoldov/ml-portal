"""Add is_active status to tool_groups

Revision ID: 0060
Revises: 0059
Create Date: 2025-02-03 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0060'
down_revision = '0059'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add is_active column to tool_groups
    op.add_column('tool_groups', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    # Remove is_active column from tool_groups
    op.drop_column('tool_groups', 'is_active')
