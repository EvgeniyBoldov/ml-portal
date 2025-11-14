"""change scope column back to string type

Revision ID: 20250118_100007
Revises: 20250118_100006
Create Date: 2025-01-18 10:00:07.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250118_100007'
down_revision = '20250118_100006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change scope column back to string type with server_default
    op.alter_column(
        'ragdocuments', 
        'scope', 
        type_=sa.String(20),
        server_default='local'
    )


def downgrade() -> None:
    # Revert scope column to enum type
    op.alter_column('ragdocuments', 'scope', 
                   type_=sa.Enum('local', 'global', name='documentscope'),
                   postgresql_using='scope::documentscope')
