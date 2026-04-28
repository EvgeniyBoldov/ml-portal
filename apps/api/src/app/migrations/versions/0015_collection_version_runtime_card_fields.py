"""Add human-readable runtime card fields to collection_versions.

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("collection_versions", sa.Column("data_description", sa.Text(), nullable=True))
    op.add_column("collection_versions", sa.Column("usage_purpose", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("collection_versions", "usage_purpose")
    op.drop_column("collection_versions", "data_description")
