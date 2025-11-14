"""add tenant_id to sources and backfill from ragdocuments

Revision ID: 20251113_220000
Revises: 20250113_170000
Create Date: 2025-11-13 22:00:00

"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251113_220000"
down_revision = "20250113_170000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add tenant_id column as nullable first
    op.add_column(
        "sources",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # 2) Backfill tenant_id from ragdocuments by matching source_id to ragdocuments.id
    op.execute(
        """
        UPDATE sources s
        SET tenant_id = r.tenant_id
        FROM ragdocuments r
        WHERE r.id = s.source_id AND s.tenant_id IS NULL
        """
    )

    # 3) Create index for tenant_id for performance
    op.create_index("ix_sources_tenant_id", "sources", ["tenant_id"], unique=False)

    # 4) Add FK constraint to tenants
    op.create_foreign_key(
        constraint_name="fk_sources_tenant_id_tenants",
        source_table="sources",
        referent_table="tenants",
        local_cols=["tenant_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # 5) Make tenant_id NOT NULL (after backfill)
    op.alter_column("sources", "tenant_id", nullable=False)


def downgrade() -> None:
    # Drop FK, index, and column in reverse order
    op.alter_column("sources", "tenant_id", nullable=True)
    op.drop_constraint("fk_sources_tenant_id_tenants", "sources", type_="foreignkey")
    op.drop_index("ix_sources_tenant_id", table_name="sources")
    op.drop_column("sources", "tenant_id")
