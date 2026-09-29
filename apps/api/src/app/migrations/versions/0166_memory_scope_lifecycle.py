"""Add scheduled deletion lifecycle to memory scopes and their records.

Revision ID: 0166
Revises: 0165
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0166"
down_revision = "0165"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("memory_scopes", "memory_claims", "memory_items"):
        op.add_column(table, sa.Column("lifecycle_status", sa.String(20), nullable=False, server_default="active"))
        op.add_column(table, sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True))
        op.add_column(table, sa.Column("deprecated_by", postgresql.UUID(as_uuid=True),
                                      sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True))
        op.add_column(table, sa.Column("deprecated_reason", sa.Text(), nullable=True))
        op.add_column(table, sa.Column("retention_days", sa.Integer(), nullable=False, server_default="14"))
        op.add_column(table, sa.Column("delete_cascade", sa.Boolean(), nullable=False, server_default=sa.false()))
        op.add_column(table, sa.Column("deprecated_root_kind", sa.String(32), nullable=True))
        op.add_column(table, sa.Column("deprecated_root_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_index(f"ix_{table}_lifecycle_status", table, ["lifecycle_status"])
        op.create_index(f"ix_{table}_deprecated_at", table, ["deprecated_at"])
        op.create_index(f"ix_{table}_deprecated_root_kind", table, ["deprecated_root_kind"])
        op.create_index(f"ix_{table}_deprecated_root_id", table, ["deprecated_root_id"])


def downgrade() -> None:
    for table in ("memory_items", "memory_claims", "memory_scopes"):
        for suffix in ("deprecated_root_id", "deprecated_root_kind", "deprecated_at", "lifecycle_status"):
            op.drop_index(f"ix_{table}_{suffix}", table_name=table)
        op.drop_column(table, "deprecated_root_id")
        op.drop_column(table, "deprecated_root_kind")
        op.drop_column(table, "delete_cascade")
        op.drop_column(table, "retention_days")
        op.drop_column(table, "deprecated_reason")
        op.drop_column(table, "deprecated_by")
        op.drop_column(table, "deprecated_at")
        op.drop_column(table, "lifecycle_status")
