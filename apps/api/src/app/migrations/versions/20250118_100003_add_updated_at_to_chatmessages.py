"""add updated_at column to chatmessages

Revision ID: 20250118_100003
Revises: 20250118_100002
Create Date: 2025-01-18 10:00:03.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250118_100003'
down_revision = '20250118_100002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add updated_at column to chatmessages table
    op.add_column('chatmessages', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')))


def downgrade() -> None:
    # Drop column
    op.drop_column('chatmessages', 'updated_at')
