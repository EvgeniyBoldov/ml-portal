"""extend lifecycle cascade fields and cover chats/sandbox

Revision ID: 0051
Revises: 0050
Create Date: 2026-06-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


BASE_LIFECYCLE_TABLES = ("tenants", "users", "collections", "agents", "rbac_rules")
NEW_LIFECYCLE_TABLES = ("chats", "sandbox_sessions")
ALL_LIFECYCLE_TABLES = BASE_LIFECYCLE_TABLES + NEW_LIFECYCLE_TABLES


def _add_base_lifecycle_columns(table_name: str) -> None:
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


def _drop_base_lifecycle_columns(table_name: str) -> None:
    op.drop_index(f"ix_{table_name}_deprecated_at", table_name=table_name)
    op.drop_index(f"ix_{table_name}_lifecycle_status", table_name=table_name)
    op.drop_constraint(f"fk_{table_name}_deprecated_by_users", table_name, type_="foreignkey")
    op.drop_column(table_name, "retention_days")
    op.drop_column(table_name, "deprecated_reason")
    op.drop_column(table_name, "deprecated_by")
    op.drop_column(table_name, "deprecated_at")
    op.drop_column(table_name, "lifecycle_status")


def _add_cascade_columns(table_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column("delete_cascade", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        table_name,
        sa.Column("deprecated_root_kind", sa.String(length=32), nullable=True),
    )
    op.add_column(
        table_name,
        sa.Column("deprecated_root_id", sa.UUID(), nullable=True),
    )
    op.create_index(f"ix_{table_name}_deprecated_root_kind", table_name, ["deprecated_root_kind"], unique=False)
    op.create_index(f"ix_{table_name}_deprecated_root_id", table_name, ["deprecated_root_id"], unique=False)


def _drop_cascade_columns(table_name: str) -> None:
    op.drop_index(f"ix_{table_name}_deprecated_root_id", table_name=table_name)
    op.drop_index(f"ix_{table_name}_deprecated_root_kind", table_name=table_name)
    op.drop_column(table_name, "deprecated_root_id")
    op.drop_column(table_name, "deprecated_root_kind")
    op.drop_column(table_name, "delete_cascade")


def upgrade() -> None:
    for table_name in NEW_LIFECYCLE_TABLES:
        _add_base_lifecycle_columns(table_name)

    for table_name in ALL_LIFECYCLE_TABLES:
        _add_cascade_columns(table_name)


def downgrade() -> None:
    for table_name in reversed(ALL_LIFECYCLE_TABLES):
        _drop_cascade_columns(table_name)

    for table_name in reversed(NEW_LIFECYCLE_TABLES):
        _drop_base_lifecycle_columns(table_name)
