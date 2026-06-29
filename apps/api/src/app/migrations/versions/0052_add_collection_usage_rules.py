"""add collection usage rules

Revision ID: 0052
Revises: 0051
Create Date: 2026-06-26 16:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return any(col.get("name") == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("collection_versions", "usage_rules"):
        op.add_column("collection_versions", sa.Column("usage_rules", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("collection_versions", "usage_rules"):
        op.drop_column("collection_versions", "usage_rules")
