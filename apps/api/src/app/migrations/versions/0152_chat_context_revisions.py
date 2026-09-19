"""Add revision guards and canonical item vocabulary for chat context.

Revision ID: 0152
Revises: 0151
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0152"
down_revision = "0151"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "chat_context_heads",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("chat_id", uuid, sa.ForeignKey("chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sandbox_branch_id", uuid, sa.ForeignKey("sandbox_branches.id", ondelete="CASCADE"), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_through_turn_id", uuid, sa.ForeignKey("chat_turns.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_through_turn_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("uq_chat_context_heads_chat_root", "chat_context_heads", ["chat_id"], unique=True,
                    postgresql_where=sa.text("sandbox_branch_id IS NULL"))
    op.create_index("uq_chat_context_heads_chat_branch", "chat_context_heads", ["chat_id", "sandbox_branch_id"], unique=True,
                    postgresql_where=sa.text("sandbox_branch_id IS NOT NULL"))
    op.add_column("chat_memory_items", sa.Column("source_turn_order", sa.Integer(), nullable=False, server_default="0"))
    op.drop_constraint("ck_chat_memory_items_kind", "chat_memory_items", type_="check")
    op.create_check_constraint(
        "ck_chat_memory_items_kind", "chat_memory_items",
        "kind IN ('scope', 'goal', 'term_binding', 'artifact_ref', 'open_loop', 'decision', 'recent_anchor', 'task_result_ref', 'open_question', 'chat_fact', 'summary')",
    )
    # Do not rewrite chat history in a schema migration. Deployments that
    # already have duplicate active rows must run the explicit, audited
    # application backfill before this revision; the unique index is the
    # deliberate safety gate rather than a silent choice of historical state.
    op.create_index("uq_chat_memory_active_root", "chat_memory_items", ["chat_id", "kind", "item_key"], unique=True,
                    postgresql_where=sa.text("status = 'active' AND sandbox_branch_id IS NULL"))
    op.create_index("uq_chat_memory_active_branch", "chat_memory_items", ["chat_id", "sandbox_branch_id", "kind", "item_key"], unique=True,
                    postgresql_where=sa.text("status = 'active' AND sandbox_branch_id IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("uq_chat_memory_active_branch", table_name="chat_memory_items")
    op.drop_index("uq_chat_memory_active_root", table_name="chat_memory_items")
    # Preserve rows on downgrade by mapping only vocabulary unavailable in
    # 0151 to its historical neutral categories; no rows are deleted.
    op.execute("""
        UPDATE chat_memory_items
        SET kind = CASE kind
            WHEN 'open_loop' THEN 'open_question'
            WHEN 'goal' THEN 'summary'
            WHEN 'recent_anchor' THEN 'summary'
            ELSE kind
        END
        WHERE kind IN ('open_loop', 'goal', 'recent_anchor')
    """)
    op.drop_constraint("ck_chat_memory_items_kind", "chat_memory_items", type_="check")
    op.create_check_constraint("ck_chat_memory_items_kind", "chat_memory_items",
        "kind IN ('scope', 'term_binding', 'artifact_ref', 'decision', 'open_question', 'chat_fact', 'summary', 'task_result_ref')")
    op.drop_column("chat_memory_items", "source_turn_order")
    op.drop_index("uq_chat_context_heads_chat_branch", table_name="chat_context_heads")
    op.drop_index("uq_chat_context_heads_chat_root", table_name="chat_context_heads")
    op.drop_table("chat_context_heads")
