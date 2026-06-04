"""Add unique constraint on collections.slug.

Revision ID: 0044
Revises: 0043
Create Date: 2026-06-04 13:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create unique constraint on collections.slug (globally unique)
    op.create_unique_constraint(
        "uq_collections_slug",
        "collections",
        ["slug"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_collections_slug", "collections", type_="unique")
