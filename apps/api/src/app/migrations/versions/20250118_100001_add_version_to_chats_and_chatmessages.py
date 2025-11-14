"""add version column to chats and chatmessages

Revision ID: 20250118_100001
Revises: 20250118_100000
Create Date: 2025-01-18 10:00:01.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250118_100001'
down_revision = '20250118_100000'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add version column to chats table
    op.add_column('chats', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    
    # Add version column to chatmessages table
    op.add_column('chatmessages', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    # Drop columns
    op.drop_column('chatmessages', 'version')
    op.drop_column('chats', 'version')
