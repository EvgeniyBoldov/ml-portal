"""remove the unused legacy JSON plans table

Revision ID: 0056
Revises: 0055
"""

from alembic import op


revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy plan rows are intentionally not backfilled. Deployment tooling
    # takes a database backup before applying this migration.
    op.drop_table("plans")


def downgrade() -> None:
    raise RuntimeError("legacy plans table is intentionally not restorable")

