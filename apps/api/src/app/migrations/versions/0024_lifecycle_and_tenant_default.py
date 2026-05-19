"""Add unified lifecycle fields and platform default tenant flag.

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


LIFECYCLE_TABLES = ("tenants", "users", "collections", "agents", "rbac_rules")


def _add_lifecycle_columns(table_name: str) -> None:
    op.add_column(table_name, sa.Column("lifecycle_status", sa.String(length=20), nullable=False, server_default="active"))
    op.add_column(table_name, sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(table_name, sa.Column("deprecated_by", sa.UUID(), nullable=True))
    op.add_column(table_name, sa.Column("deprecated_reason", sa.Text(), nullable=True))
    op.add_column(table_name, sa.Column("retention_days", sa.Integer(), nullable=False, server_default="14"))

    op.create_foreign_key(
        f"fk_{table_name}_deprecated_by_users",
        table_name,
        "users",
        ["deprecated_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(f"ix_{table_name}_lifecycle_status", table_name, ["lifecycle_status"], unique=False)
    op.create_index(f"ix_{table_name}_deprecated_at", table_name, ["deprecated_at"], unique=False)


def _drop_lifecycle_columns(table_name: str) -> None:
    op.drop_index(f"ix_{table_name}_deprecated_at", table_name=table_name)
    op.drop_index(f"ix_{table_name}_lifecycle_status", table_name=table_name)
    op.drop_constraint(f"fk_{table_name}_deprecated_by_users", table_name, type_="foreignkey")
    op.drop_column(table_name, "retention_days")
    op.drop_column(table_name, "deprecated_reason")
    op.drop_column(table_name, "deprecated_by")
    op.drop_column(table_name, "deprecated_at")
    op.drop_column(table_name, "lifecycle_status")


def upgrade() -> None:
    op.add_column("tenants", sa.Column("is_platform_default", sa.Boolean(), nullable=False, server_default=sa.false()))

    for table_name in LIFECYCLE_TABLES:
        _add_lifecycle_columns(table_name)

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_tenants_platform_default_true
        ON tenants (is_platform_default)
        WHERE is_platform_default = TRUE
        """
    )

    # Backfill exactly one default tenant.
    op.execute(
        """
        WITH candidate AS (
          SELECT id
          FROM tenants
          WHERE is_active = TRUE
          ORDER BY created_at ASC NULLS LAST
          LIMIT 1
        )
        UPDATE tenants t
        SET is_platform_default = TRUE
        FROM candidate c
        WHERE t.id = c.id
          AND NOT EXISTS (
              SELECT 1 FROM tenants x WHERE x.is_platform_default = TRUE
          )
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_tenants_platform_default_true")

    for table_name in reversed(LIFECYCLE_TABLES):
        _drop_lifecycle_columns(table_name)

    op.drop_column("tenants", "is_platform_default")
