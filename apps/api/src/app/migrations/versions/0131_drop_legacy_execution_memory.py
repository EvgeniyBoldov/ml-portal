"""Drop unused legacy execution memory state.

Revision ID: 0131
Revises: 0130
"""
from __future__ import annotations

from alembic import op


revision = "0131"
down_revision = "0130"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("execution_memories")


def downgrade() -> None:
    # This legacy structure intentionally has no downgrade recreation: it was
    # not read by any runtime path and its historical JSON payload has no
    # target-model equivalent.
    pass
