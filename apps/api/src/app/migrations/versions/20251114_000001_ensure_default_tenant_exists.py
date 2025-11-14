"""ensure default tenant exists for local development

Revision ID: 20251114_000001
Revises: 20251114_000000
Create Date: 2025-11-14 00:00:01

"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251114_000001"
down_revision = "20251114_000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Ensure default tenant exists for local development.
    This tenant ID is hardcoded in factory.py as fallback for local env.
    """
    
    # Insert default tenant if it doesn't exist
    op.execute(
        """
        INSERT INTO tenants (id, name, is_active, created_at, updated_at)
        VALUES (
            'fb983a10-c5f8-4840-a9d3-856eea0dc729'::uuid,
            'default',
            true,
            now(),
            now()
        )
        ON CONFLICT (id) DO NOTHING;
        """
    )


def downgrade() -> None:
    """Remove default tenant"""
    op.execute(
        """
        DELETE FROM tenants 
        WHERE id = 'fb983a10-c5f8-4840-a9d3-856eea0dc729'::uuid;
        """
    )
