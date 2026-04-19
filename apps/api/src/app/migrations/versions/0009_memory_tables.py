"""Create runtime memory tables (facts, dialogue_summaries).

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-19

Introduces the persistence layer for the new memory architecture:

    * `facts`              — typed, scope-aware, supersede-based
    * `dialogue_summaries` — structured per-chat (one row per chat)

These tables are written by `MemoryWriter.finalize` at turn end and
read by `MemoryBuilder.build` at turn start. The legacy
`runs.memory_state` JSONB blob and the monolithic `chat_summaries`
table will be retired in later migrations once the pipeline fully
migrates; for now they co-exist without touching them.

Down-migration drops both tables cleanly — no data bridges.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------- facts ---
    op.create_table(
        "facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "chat_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chats.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1.0"),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_ref", sa.String(128), nullable=True),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "superseded_by", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "user_visible",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "scope IN ('chat', 'user', 'tenant')",
            name="ck_facts_scope",
        ),
        sa.CheckConstraint(
            "source IN ('user_utterance', 'agent_result', 'system')",
            name="ck_facts_source",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_facts_confidence_range",
        ),
    )
    # Partial indexes on "active" rows — most reads filter superseded_by IS NULL.
    op.create_index(
        "ix_facts_scope_subject_active",
        "facts",
        ["scope", "subject"],
        postgresql_where=sa.text("superseded_by IS NULL"),
    )
    op.create_index(
        "ix_facts_user_scope",
        "facts",
        ["user_id", "scope"],
        postgresql_where=sa.text("superseded_by IS NULL"),
    )
    op.create_index(
        "ix_facts_chat_observed",
        "facts",
        ["chat_id", "observed_at"],
    )
    op.create_index(
        "ix_facts_tenant_scope",
        "facts",
        ["tenant_id", "scope"],
    )

    # ------------------------------------------------ dialogue_summaries ---
    op.create_table(
        "dialogue_summaries",
        sa.Column(
            "chat_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chats.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "goals", postgresql.JSONB, nullable=False, server_default="[]"
        ),
        sa.Column(
            "done", postgresql.JSONB, nullable=False, server_default="[]"
        ),
        sa.Column(
            "entities", postgresql.JSONB, nullable=False, server_default="{}"
        ),
        sa.Column(
            "open_questions",
            postgresql.JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column("raw_tail", sa.Text, nullable=False, server_default=""),
        sa.Column(
            "last_updated_turn",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_dialogue_summaries_updated",
        "dialogue_summaries",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_dialogue_summaries_updated", table_name="dialogue_summaries")
    op.drop_table("dialogue_summaries")

    op.drop_index("ix_facts_tenant_scope", table_name="facts")
    op.drop_index("ix_facts_chat_observed", table_name="facts")
    op.drop_index("ix_facts_user_scope", table_name="facts")
    op.drop_index("ix_facts_scope_subject_active", table_name="facts")
    op.drop_table("facts")
