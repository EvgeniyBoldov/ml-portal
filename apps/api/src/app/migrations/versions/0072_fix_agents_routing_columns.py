"""Fix missing routing columns in agents table.

Revision ID: 0072_fix_agents_routing_columns
Revises: 0071_merge_main_heads
Create Date: 2026-02-17
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0072_fix_agents_routing_columns"
down_revision: Union[str, Sequence[str], None] = "0071_merge_main_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("agents", "tag"):
        op.add_column("agents", sa.Column("tag", sa.String(length=100), nullable=True))

    if not _has_column("agents", "category"):
        op.add_column("agents", sa.Column("category", sa.String(length=100), nullable=True))

    if not _has_column("agents", "routing_example"):
        op.add_column("agents", sa.Column("routing_example", sa.Text(), nullable=True))

    if not _has_column("agents", "is_routable"):
        op.add_column("agents", sa.Column("is_routable", sa.Boolean(), nullable=True))
        op.execute("UPDATE agents SET is_routable = false WHERE is_routable IS NULL")
        op.alter_column("agents", "is_routable", nullable=False, server_default=sa.text("false"))


def downgrade() -> None:
    if _has_column("agents", "is_routable"):
        op.drop_column("agents", "is_routable")
    if _has_column("agents", "routing_example"):
        op.drop_column("agents", "routing_example")
    if _has_column("agents", "category"):
        op.drop_column("agents", "category")
    if _has_column("agents", "tag"):
        op.drop_column("agents", "tag")
