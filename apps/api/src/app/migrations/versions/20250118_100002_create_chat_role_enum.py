"""create chat_role_enum

Revision ID: 20250118_100002
Revises: 20250118_100001
Create Date: 2025-01-18 10:00:02.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250118_100002'
down_revision = '20250118_100001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create chat_role_enum
    op.execute("CREATE TYPE chat_role_enum AS ENUM ('system', 'user', 'assistant', 'tool')")
    
    # Update chatmessages.role column to use the enum
    op.alter_column('chatmessages', 'role', 
                   type_=sa.Enum('system', 'user', 'assistant', 'tool', name='chat_role_enum'),
                   postgresql_using='role::chat_role_enum')


def downgrade() -> None:
    # Revert chatmessages.role column to string
    op.alter_column('chatmessages', 'role', type_=sa.String(20))
    
    # Drop the enum type
    op.execute("DROP TYPE chat_role_enum")
