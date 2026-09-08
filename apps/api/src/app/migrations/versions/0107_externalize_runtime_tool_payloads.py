"""Store large runtime tool payloads outside PostgreSQL.

Revision ID: 0107
Revises: 0106
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runtime_tool_results", sa.Column("payload_ref", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("runtime_tool_results", "payload_ref")
