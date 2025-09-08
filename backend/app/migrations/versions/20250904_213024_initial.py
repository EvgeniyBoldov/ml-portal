"""initial

Revision ID: 20250904_213024
Revises: 
Create Date: 2025-09-04 21:30:24.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250904_213024'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    bind = op.get_bind()

    # 1) Ensure ENUM exists (idempotent)
    role_enum = postgresql.ENUM('admin', 'editor', 'reader', name='role_enum', create_type=True)
    role_enum.create(bind, checkfirst=True)

    # 2) Tables (use create_type=False so SQLA doesn't try to recreate the enum)
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('login', sa.String(length=255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', postgresql.ENUM('admin', 'editor', 'reader', name='role_enum', create_type=False), nullable=False, server_default='reader'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )

    op.create_index('ix_users_login', 'users', ['login'], unique=True)

    # пример дополнительной таблицы (оставь/удали под свой проект)
    # op.create_table('documents', ...)

def downgrade() -> None:
    bind = op.get_bind()

    # Удаляем таблицу(ы), которые ссылались на enum
    op.drop_index('ix_users_login', table_name='users')
    op.drop_table('users')

    # Дропаем тип, если он больше не используется
    role_enum = postgresql.ENUM('admin', 'editor', 'reader', name='role_enum', create_type=True)
    try:
        role_enum.drop(bind, checkfirst=True)
    except Exception:
        # если ещё чем-то используется — пропускаем
        pass
