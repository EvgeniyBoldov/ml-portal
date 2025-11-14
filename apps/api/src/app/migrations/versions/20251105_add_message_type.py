"""add message_type to chatmessages

Revision ID: 20251105_add_message_type
Revises: 
Create Date: 2025-11-05 23:25:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251105_add_message_type'
down_revision = '20251105_000000'
branch_labels = None
depends_on = None


def upgrade():
    # Add message_type column with default value
    op.add_column('chatmessages', 
        sa.Column('message_type', sa.String(length=50), nullable=False, server_default='text')
    )
    
    # Create index for message_type for future filtering
    op.create_index('ix_chatmessages_message_type', 'chatmessages', ['message_type'])


def downgrade():
    op.drop_index('ix_chatmessages_message_type', table_name='chatmessages')
    op.drop_column('chatmessages', 'message_type')
