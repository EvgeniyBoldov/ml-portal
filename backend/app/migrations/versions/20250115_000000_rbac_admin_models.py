"""rbac admin models

Revision ID: 20250115_000000_rbac_admin_models
Revises: 20250912_104656_add_chat_tags
Create Date: 2025-01-15 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250115_000000_rbac_admin_models'
down_revision = '20250912_104656_add_chat_tags'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing ENUM type and replace with VARCHAR + CHECK constraint
    op.execute("DROP TYPE IF EXISTS role_enum CASCADE")
    
    # Add email column to users
    op.add_column('users', sa.Column('email', sa.String(255), nullable=True))
    op.create_index('ix_users_email', 'users', ['email'])
    
    # Change role column from ENUM to VARCHAR with CHECK constraint
    op.alter_column('users', 'role', type_=sa.String(20), existing_type=postgresql.ENUM('admin', 'editor', 'reader', name='role_enum'))
    op.create_check_constraint('ck_users_role', 'users', "role IN ('admin', 'editor', 'reader')")
    
    # Update user_tokens table
    op.add_column('user_tokens', sa.Column('scopes', postgresql.JSON(astext_type=sa.Text()), nullable=True))
    op.add_column('user_tokens', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    op.alter_column('user_tokens', 'revoked', new_column_name='revoked_at', type_=sa.DateTime(timezone=True))
    op.alter_column('user_tokens', 'revoked_at', nullable=True)
    
    # Create password_reset_tokens table
    op.create_table('password_reset_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token_hash')
    )
    op.create_index('ix_password_reset_tokens_user_id', 'password_reset_tokens', ['user_id'])
    op.create_index('ix_password_reset_tokens_expires_at', 'password_reset_tokens', ['expires_at'])
    op.create_index('ix_password_reset_tokens_used_at', 'password_reset_tokens', ['used_at'])
    
    # Add TTL cleanup function for password reset tokens (expires after 1 hour)
    op.execute("""
        CREATE OR REPLACE FUNCTION cleanup_expired_password_reset_tokens()
        RETURNS void AS $$
        BEGIN
            DELETE FROM password_reset_tokens 
            WHERE expires_at < NOW() OR used_at IS NOT NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)
    
    # Create audit_logs table
    op.create_table('audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('actor_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action', sa.String(50), nullable=False),
        sa.Column('object_type', sa.String(50), nullable=True),
        sa.Column('object_id', sa.String(255), nullable=True),
        sa.Column('meta', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('ip', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('request_id', sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_audit_logs_ts', 'audit_logs', ['ts'])
    op.create_index('ix_audit_logs_actor_user_id', 'audit_logs', ['actor_user_id'])
    op.create_index('ix_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('ix_audit_logs_object_type', 'audit_logs', ['object_type'])
    op.create_index('ix_audit_logs_object_id', 'audit_logs', ['object_id'])
    op.create_index('ix_audit_logs_request_id', 'audit_logs', ['request_id'])


def downgrade() -> None:
    # Drop new tables
    op.drop_table('audit_logs')
    op.drop_table('password_reset_tokens')
    
    # Revert user_tokens changes
    op.alter_column('user_tokens', 'revoked_at', new_column_name='revoked', type_=sa.Boolean())
    op.alter_column('user_tokens', 'revoked', nullable=False, server_default=sa.text('false'))
    op.drop_column('user_tokens', 'expires_at')
    op.drop_column('user_tokens', 'scopes')
    
    # Revert users changes
    op.drop_constraint('ck_users_role', 'users', type_='check')
    op.alter_column('users', 'role', type_=postgresql.ENUM('admin', 'editor', 'reader', name='role_enum'))
    op.drop_index('ix_users_email', 'users')
    op.drop_column('users', 'email')
    
    # Recreate ENUM type
    op.execute("CREATE TYPE role_enum AS ENUM ('admin', 'editor', 'reader')")
