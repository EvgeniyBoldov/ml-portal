"""allow detached chat artifacts

Revision ID: 0053
Revises: 0052
Create Date: 2026-06-30 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def _chat_id_nullable() -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    for column in inspector.get_columns("chat_attachments"):
        if column.get("name") == "chat_id":
            return bool(column.get("nullable"))
    return False


def upgrade() -> None:
    if not _chat_id_nullable():
        op.alter_column("chat_attachments", "chat_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    if _chat_id_nullable():
        op.alter_column("chat_attachments", "chat_id", existing_type=sa.UUID(), nullable=False)
