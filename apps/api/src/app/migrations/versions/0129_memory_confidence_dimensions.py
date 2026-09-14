"""Separate extraction, project-resolution and source-trust confidence."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0129"
down_revision = "0128"
branch_labels = None
depends_on = None


def _columns(table: str) -> None:
    op.add_column(table, sa.Column("extraction_confidence", sa.Float(), nullable=False, server_default="1"))
    op.add_column(table, sa.Column("project_resolution_confidence", sa.Float(), nullable=False, server_default="0"))
    op.add_column(table, sa.Column("source_trust", sa.Float(), nullable=False, server_default="1"))


def upgrade() -> None:
    _columns("memory_items")
    _columns("memory_claims")
    op.execute(sa.text("UPDATE memory_items SET extraction_confidence = confidence"))
    op.execute(sa.text("UPDATE memory_claims SET extraction_confidence = confidence"))


def downgrade() -> None:
    for table in ("memory_claims", "memory_items"):
        op.drop_column(table, "source_trust")
        op.drop_column(table, "project_resolution_confidence")
        op.drop_column(table, "extraction_confidence")
