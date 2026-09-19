"""Add typed chat-local working context.

Revision ID: 0151
Revises: 0150
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0151"
down_revision = "0150"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "chat_memory_items",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("chat_id", uuid, sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sandbox_branch_id", uuid, sa.ForeignKey("sandbox_branches.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("item_key", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source_turn_id", uuid, sa.ForeignKey("chat_turns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_message_id", uuid, sa.ForeignKey("chatmessages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_run_id", uuid, nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("kind IN ('scope', 'term_binding', 'artifact_ref', 'decision', 'open_question', 'chat_fact', 'summary', 'task_result_ref')", name="ck_chat_memory_items_kind"),
        sa.CheckConstraint("status IN ('active', 'superseded', 'closed', 'expired')", name="ck_chat_memory_items_status"),
    )
    op.create_index("ix_chat_memory_items_chat_active", "chat_memory_items", ["chat_id", "status", "updated_at"])
    op.create_index("ix_chat_memory_items_branch_active", "chat_memory_items", ["sandbox_branch_id", "status", "updated_at"])
    op.create_index("ix_chat_memory_items_source_turn", "chat_memory_items", ["source_turn_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_memory_items_source_turn", table_name="chat_memory_items")
    op.drop_index("ix_chat_memory_items_branch_active", table_name="chat_memory_items")
    op.drop_index("ix_chat_memory_items_chat_active", table_name="chat_memory_items")
    op.drop_table("chat_memory_items")
