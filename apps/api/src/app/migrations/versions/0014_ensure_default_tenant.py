"""Ensure default tenant exists for local dev"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0014_ensure_default_tenant"
down_revision = "0013_create_state_engine_tables"
branch_labels = None
depends_on = None


DEFAULT_TENANT_ID = "fb983a10-c5f8-4840-a9d3-856eea0dc729"


def upgrade() -> None:
    op.execute(
        f"""
        INSERT INTO tenants (id, name, is_active, created_at, updated_at)
        VALUES ('{DEFAULT_TENANT_ID}'::uuid, 'default', true, now(), now())
        ON CONFLICT (id) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        DELETE FROM tenants
        WHERE id = '{DEFAULT_TENANT_ID}'::uuid;
        """
    )
