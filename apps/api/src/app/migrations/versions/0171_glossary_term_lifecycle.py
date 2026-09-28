"""Allow administrators to deactivate glossary terms."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0171"
down_revision = "0170"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "glossary_terms",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_column("glossary_terms", "is_active")
