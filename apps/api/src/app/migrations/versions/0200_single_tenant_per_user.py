"""Enforce one tenant membership per user.

Revision ID: 0200
Revises: 0199
"""
from alembic import op
import sqlalchemy as sa


revision = "0200"
down_revision = "0199"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve the existing default membership when old multi-tenant records
    # exist; otherwise keep the tenant with the smallest UUID deterministically.
    op.execute(sa.text("""
        WITH ranked AS (
            SELECT id, user_id,
                   row_number() OVER (
                       PARTITION BY user_id
                       ORDER BY is_default DESC, tenant_id ASC, id ASC
                   ) AS position
            FROM user_tenants
        )
        DELETE FROM user_tenants
        WHERE id IN (SELECT id FROM ranked WHERE position > 1)
    """))
    op.execute(sa.text("UPDATE user_tenants SET is_default = TRUE WHERE is_default IS DISTINCT FROM TRUE"))
    op.create_unique_constraint(
        "uq_user_tenants_single_tenant_per_user", "user_tenants", ["user_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_user_tenants_single_tenant_per_user", "user_tenants", type_="unique"
    )
