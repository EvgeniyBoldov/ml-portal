# app/migrations/versions/20250115_120000_fix_user_tokens_and_users_schema.py
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20250115_120000_fix_schema"
down_revision = "20250912_104656_add_chat_tags"
branch_labels = None
depends_on = None

def upgrade():
    # Добавляем недостающие колонки в users
    op.add_column('users', sa.Column('email', sa.String(255), nullable=True))
    op.add_column('users', sa.Column('require_password_change', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    
    # Добавляем недостающие колонки в user_tokens
    op.add_column('user_tokens', sa.Column('scopes', postgresql.ARRAY(sa.String), nullable=True))
    op.add_column('user_tokens', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    
    # Добавляем уникальный индекс на token_hash
    op.create_index('ix_user_tokens_token_hash_unique', 'user_tokens', ['token_hash'], unique=True)
    
    # Создаем таблицу password_reset_tokens
    op.create_table(
        'password_reset_tokens',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('token_hash', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_password_reset_tokens_user_id', 'password_reset_tokens', ['user_id'])
    op.create_index('ix_password_reset_tokens_token_hash_unique', 'password_reset_tokens', ['token_hash'], unique=True)
    op.create_index('ix_password_reset_tokens_expires_at', 'password_reset_tokens', ['expires_at'])

def downgrade():
    # Удаляем таблицу password_reset_tokens
    op.drop_table('password_reset_tokens')
    
    # Удаляем индексы
    op.drop_index('ix_user_tokens_token_hash_unique', 'user_tokens')
    
    # Удаляем колонки из user_tokens
    op.drop_column('user_tokens', 'expires_at')
    op.drop_column('user_tokens', 'scopes')
    
    # Удаляем колонки из users
    op.drop_column('users', 'require_password_change')
    op.drop_column('users', 'email')
