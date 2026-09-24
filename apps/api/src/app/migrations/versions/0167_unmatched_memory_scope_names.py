"""Keep scope names mentioned by extraction when no catalog entry matches.

Revision ID: 0167
Revises: 0166
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0167"
down_revision = "0166"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memory_extraction_candidates", sa.Column(
        "unmatched_scope_names", postgresql.JSONB(), nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    ))


def downgrade() -> None:
    op.drop_column("memory_extraction_candidates", "unmatched_scope_names")
