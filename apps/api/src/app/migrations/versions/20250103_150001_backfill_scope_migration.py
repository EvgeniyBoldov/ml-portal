"""Backfill existing documents with scope migration

Revision ID: 20250103_150001
Revises: 20250103_150000
Create Date: 2025-01-03 15:00:01.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250103_150001'
down_revision = '20250103_150000'
branch_labels = None
depends_on = None


def upgrade():
    """
    Backfill existing documents:
    1. Set all existing documents to 'local' scope
    2. Set tenant_id from user's default tenant
    3. Update chunk metadata in Qdrant
    
    This migration is skipped for now as it requires existing data.
    """
    pass


def downgrade():
    """
    This migration is irreversible - backfill operations cannot be undone
    """
    pass
