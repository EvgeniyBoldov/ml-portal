"""Persist chat memory finalization jobs before Celery dispatch.

Revision ID: 0204
Revises: 0203
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0204"
down_revision = "0203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_finalize_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("runtime_run_id", sa.String(length=64), nullable=True, unique=True),
        sa.Column("chat_turn_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_memory_finalize_outbox_dispatch", "memory_finalize_outbox", ["status", "available_at"])


def downgrade() -> None:
    op.drop_index("ix_memory_finalize_outbox_dispatch", table_name="memory_finalize_outbox")
    op.drop_table("memory_finalize_outbox")
