"""Set user_tenants FKs to ON DELETE CASCADE.

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-18
"""
from __future__ import annotations

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE user_tenants DROP CONSTRAINT IF EXISTS user_tenants_user_id_fkey")
    op.execute("ALTER TABLE user_tenants DROP CONSTRAINT IF EXISTS user_tenants_tenant_id_fkey")

    op.execute(
        """
        ALTER TABLE user_tenants
        ADD CONSTRAINT user_tenants_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        """
    )
    op.execute(
        """
        ALTER TABLE user_tenants
        ADD CONSTRAINT user_tenants_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE CASCADE
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE user_tenants DROP CONSTRAINT IF EXISTS user_tenants_user_id_fkey")
    op.execute("ALTER TABLE user_tenants DROP CONSTRAINT IF EXISTS user_tenants_tenant_id_fkey")

    op.execute(
        """
        ALTER TABLE user_tenants
        ADD CONSTRAINT user_tenants_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(id)
        """
    )
    op.execute(
        """
        ALTER TABLE user_tenants
        ADD CONSTRAINT user_tenants_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        """
    )
