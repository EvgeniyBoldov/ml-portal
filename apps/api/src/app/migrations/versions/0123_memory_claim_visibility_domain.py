"""Persist the source visibility domain on semantic claims.

Revision ID: 0123
Revises: 0122
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0123"
down_revision = "0122"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "memory_claims",
        sa.Column("visibility_tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_memory_claims_visibility_tenant", "memory_claims", "tenants",
        ["visibility_tenant_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_memory_claims_visibility_tenant", "memory_claims", ["visibility_tenant_id"])
    # Existing local evidence must not be treated as company-visible after
    # the new Recall contract starts using claim text directly.
    op.execute(sa.text("""
        UPDATE memory_claims claim
        SET visibility_tenant_id = doc.tenant_id
        FROM ragdocuments doc
        WHERE claim.document_id = doc.id
          AND doc.scope = 'local'
    """))


def downgrade() -> None:
    op.drop_index("ix_memory_claims_visibility_tenant", table_name="memory_claims")
    op.drop_constraint("fk_memory_claims_visibility_tenant", "memory_claims", type_="foreignkey")
    op.drop_column("memory_claims", "visibility_tenant_id")
