"""Create api_tokens table for user API tokens (MCP/IDE)

Revision ID: 0034
Revises: 0033
Create Date: 2024-12-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0034_create_api_tokens_table'
down_revision = '0033_create_api_keys_table'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if table exists
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'api_tokens')"))
    exists = result.scalar()
    
    if not exists:
        op.create_table(
            'api_tokens',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
            sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
            sa.Column('name', sa.String(255), nullable=False),
            sa.Column('token_hash', sa.Text(), nullable=False),
            sa.Column('token_prefix', sa.String(10), nullable=False),
            sa.Column('scopes', sa.Text(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
            sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        )
        
        op.create_index('ix_api_tokens_user_id', 'api_tokens', ['user_id'])
        op.create_index('ix_api_tokens_token_prefix', 'api_tokens', ['token_prefix'])


def downgrade() -> None:
    op.drop_index('ix_api_tokens_token_prefix', table_name='api_tokens')
    op.drop_index('ix_api_tokens_user_id', table_name='api_tokens')
    op.drop_table('api_tokens')
