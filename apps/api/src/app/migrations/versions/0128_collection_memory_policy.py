"""Add an explicit collection-level durable-memory policy."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0128"
down_revision = "0127"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collections", sa.Column("memory_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("collections", "memory_enabled")
