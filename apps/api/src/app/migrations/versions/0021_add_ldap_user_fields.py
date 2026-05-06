"""
Add LDAP user fields and default tenant

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-06

"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0021"
down_revision: str | None = "0020"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # Add LDAP and profile columns to users table
    op.add_column(
        "users",
        sa.Column("auth_provider", sa.String(16), nullable=False, server_default="local")
    )
    op.add_column(
        "users",
        sa.Column("external_id", sa.String(512), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("ldap_groups", postgresql.ARRAY(sa.String), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("full_name", sa.String(255), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "users",
        sa.Column("deactivated_reason", sa.String(64), nullable=True)
    )

    # Make password_hash nullable (for LDAP users)
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.Text(),
        nullable=True
    )

    # Create unique index on (auth_provider, external_id) where external_id IS NOT NULL
    op.create_index(
        "ix_users_auth_provider_external_id",
        "users",
        ["auth_provider", "external_id"],
        unique=True,
        postgresql_where="external_id IS NOT NULL"
    )


def downgrade() -> None:
    # Drop index
    op.drop_index("ix_users_auth_provider_external_id", table_name="users")

    # Restore password_hash as NOT NULL (with dummy value for existing NULLs if any)
    op.execute("UPDATE users SET password_hash = 'LEGACY' WHERE password_hash IS NULL;")
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.Text(),
        nullable=False
    )

    # Drop columns
    op.drop_column("users", "deactivated_reason")
    op.drop_column("users", "deactivated_at")
    op.drop_column("users", "full_name")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "ldap_groups")
    op.drop_column("users", "external_id")
    op.drop_column("users", "auth_provider")
