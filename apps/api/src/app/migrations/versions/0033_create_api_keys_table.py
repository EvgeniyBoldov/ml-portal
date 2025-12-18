"""Create api_keys table for IDE plugin authentication

Revision ID: 0033_create_api_keys_table
Revises: 0032_create_audit_logs_table
Create Date: 2025-12-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0033_create_api_keys_table'
down_revision: Union[str, None] = '0032_create_audit_logs_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('key_prefix', sa.String(12), nullable=False),
        sa.Column('key_hash', sa.String(64), unique=True, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('scopes', postgresql.JSONB, server_default='[]'),
        sa.Column('allowed_tools', postgresql.JSONB, nullable=True),
        sa.Column('allowed_prompts', postgresql.JSONB, nullable=True),
        sa.Column('rate_limit_rpm', sa.Integer, nullable=True),
        sa.Column('rate_limit_rph', sa.Integer, nullable=True),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    
    # Create indexes
    op.create_index('ix_api_keys_key_hash', 'api_keys', ['key_hash'])
    op.create_index('ix_api_keys_user_id', 'api_keys', ['user_id'])
    op.create_index('ix_api_keys_tenant_id', 'api_keys', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_api_keys_tenant_id', table_name='api_keys')
    op.drop_index('ix_api_keys_user_id', table_name='api_keys')
    op.drop_index('ix_api_keys_key_hash', table_name='api_keys')
    op.drop_table('api_keys')
