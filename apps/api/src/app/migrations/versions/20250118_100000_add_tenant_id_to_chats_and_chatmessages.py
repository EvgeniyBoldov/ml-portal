"""add tenant_id to chats and chatmessages

Revision ID: 20250118_100000
Revises: 20250115_120000_fix_user_tokens_and_users_schema
Create Date: 2025-01-18 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250118_100000'
down_revision = '20250115_120000_fix_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add tenant_id column to chats table
    op.add_column('chats', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False, server_default='fb983a10-c5f8-4840-a9d3-856eea0dc729'))
    
    # Add tenant_id column to chatmessages table  
    op.add_column('chatmessages', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False, server_default='fb983a10-c5f8-4840-a9d3-856eea0dc729'))
    
    # Create indexes for tenant_id columns
    op.create_index('ix_chats_tenant_id', 'chats', ['tenant_id'])
    op.create_index('ix_chatmessages_tenant_id', 'chatmessages', ['tenant_id'])
    
    # Create composite indexes for multi-tenant queries
    op.create_index('ix_chats_tenant_created', 'chats', ['tenant_id', 'created_at'])
    op.create_index('ix_chats_tenant_owner', 'chats', ['tenant_id', 'owner_id'])
    op.create_index('ix_chats_tenant_name', 'chats', ['tenant_id', 'name'])
    op.create_index('ix_chatmessages_tenant_created', 'chatmessages', ['tenant_id', 'created_at'])
    op.create_index('ix_chatmessages_tenant_chat', 'chatmessages', ['tenant_id', 'chat_id'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_chatmessages_tenant_chat', 'chatmessages')
    op.drop_index('ix_chatmessages_tenant_created', 'chatmessages')
    op.drop_index('ix_chats_tenant_name', 'chats')
    op.drop_index('ix_chats_tenant_owner', 'chats')
    op.drop_index('ix_chats_tenant_created', 'chats')
    op.drop_index('ix_chatmessages_tenant_id', 'chatmessages')
    op.drop_index('ix_chats_tenant_id', 'chats')
    
    # Drop columns
    op.drop_column('chatmessages', 'tenant_id')
    op.drop_column('chats', 'tenant_id')
