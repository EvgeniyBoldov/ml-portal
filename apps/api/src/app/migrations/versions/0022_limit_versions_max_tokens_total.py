"""Add max_tokens_total to limit_versions.

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-16
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "limit_versions" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("limit_versions")}
    if "max_tokens_total" in columns:
        return
    op.add_column(
        "limit_versions",
        sa.Column("max_tokens_total", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "limit_versions" not in inspector.get_table_names():
        return
    columns = {col["name"] for col in inspector.get_columns("limit_versions")}
    if "max_tokens_total" not in columns:
        return
    op.drop_column("limit_versions", "max_tokens_total")
