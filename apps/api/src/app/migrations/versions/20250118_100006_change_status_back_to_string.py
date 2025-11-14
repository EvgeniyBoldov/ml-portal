"""change status column back to string type

Revision ID: 20250118_100006
Revises: 20250118_100005
Create Date: 2025-01-18 10:00:06.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '20250118_100006'
down_revision = '20250118_100005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change status column back to string type
    op.alter_column('ragdocuments', 'status', type_=sa.String(20))


def downgrade() -> None:
    # Revert status column to enum type
    op.alter_column('ragdocuments', 'status', 
                   type_=sa.Enum('uploading', 'processing', 'processed', 'failed', 'archived', name='documentstatus'),
                   postgresql_using='status::documentstatus')
