"""add chat-scoped artifact references

Revision ID: 0054
Revises: 0053
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_artifact_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_kind", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=255), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("display_name", sa.String(length=512), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("metadata_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "target_kind", "target_id", name="uq_chat_artifact_reference_target"),
    )
    op.create_index(
        "ix_chat_artifact_references_chat_created",
        "chat_artifact_references",
        ["chat_id", "created_at"],
    )
    op.create_index(
        "ix_chat_artifact_references_target",
        "chat_artifact_references",
        ["target_kind", "target_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_artifact_references_target", table_name="chat_artifact_references")
    op.drop_index("ix_chat_artifact_references_chat_created", table_name="chat_artifact_references")
    op.drop_table("chat_artifact_references")
