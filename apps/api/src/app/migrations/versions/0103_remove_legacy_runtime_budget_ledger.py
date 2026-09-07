"""Remove the superseded transactional runtime budget ledger.

Revision ID: 0103
Revises: 0102
"""
from __future__ import annotations

from alembic import op


revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Budget enforcement belongs to the canonical runtime budget registry and
    # its event snapshots. Keeping these tables would preserve a second,
    # unused interpretation of the same counters.
    op.execute("DROP TABLE IF EXISTS runtime_budget_entries CASCADE")
    op.execute("DROP TABLE IF EXISTS runtime_budget_counters CASCADE")


def downgrade() -> None:
    raise RuntimeError("legacy runtime budget ledger removal is irreversible")
