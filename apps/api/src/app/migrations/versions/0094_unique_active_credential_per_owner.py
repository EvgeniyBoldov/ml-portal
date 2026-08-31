"""Enforce one active credential per instance/owner scope.

Revision ID: 0094
Revises: 0093

Credential rows are user/tenant data.  Existing duplicates must be resolved
through the controlled admin deduplication operation before this schema-only
migration is applied; this revision never silently changes encrypted payloads
or their active state.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None


_DUPLICATE_ACTIVE_SCOPE_SQL = sa.text(
    """
    SELECT instance_id
    FROM credentials
    WHERE is_active = true
    GROUP BY instance_id, owner_platform, owner_user_id, owner_tenant_id
    HAVING count(*) > 1
    LIMIT 1
    """
)


def upgrade() -> None:
    duplicate = op.get_bind().execute(_DUPLICATE_ACTIVE_SCOPE_SQL).first()
    if duplicate is not None:
        raise RuntimeError(
            "Active credential duplicates exist. Run the controlled admin "
            "credential deduplication operation before applying revision 0094."
        )

    op.drop_index("ix_credential_user_lookup", table_name="credentials")
    op.drop_index("ix_credential_tenant_lookup", table_name="credentials")
    op.drop_index("ix_credential_platform_lookup", table_name="credentials")
    op.create_index(
        "ix_credential_user_lookup",
        "credentials",
        ["owner_user_id", "instance_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true AND owner_user_id IS NOT NULL"),
    )
    op.create_index(
        "ix_credential_tenant_lookup",
        "credentials",
        ["owner_tenant_id", "instance_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true AND owner_tenant_id IS NOT NULL"),
    )
    op.create_index(
        "ix_credential_platform_lookup",
        "credentials",
        ["owner_platform", "instance_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true AND owner_platform = true"),
    )


def downgrade() -> None:
    op.drop_index("ix_credential_user_lookup", table_name="credentials")
    op.drop_index("ix_credential_tenant_lookup", table_name="credentials")
    op.drop_index("ix_credential_platform_lookup", table_name="credentials")
    op.create_index(
        "ix_credential_user_lookup",
        "credentials",
        ["owner_user_id", "instance_id"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "ix_credential_tenant_lookup",
        "credentials",
        ["owner_tenant_id", "instance_id"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "ix_credential_platform_lookup",
        "credentials",
        ["owner_platform", "instance_id"],
        unique=False,
        postgresql_where=sa.text("is_active = true"),
    )
