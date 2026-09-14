"""Add durable decision items to semantic memory.

Revision ID: 0130
Revises: 0129
"""
from __future__ import annotations

from alembic import op


revision = "0130"
down_revision = "0129"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_memory_items_type", "memory_items", type_="check")
    op.create_check_constraint(
        "ck_memory_items_type", "memory_items",
        "item_type IN ('description', 'relationship', 'rule', 'constraint', 'procedure', 'decision')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_memory_items_type", "memory_items", type_="check")
    op.create_check_constraint(
        "ck_memory_items_type", "memory_items",
        "item_type IN ('description', 'relationship', 'rule', 'constraint', 'procedure')",
    )
