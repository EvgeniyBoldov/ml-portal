"""Create chats and chatmessages tables"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0005_create_chats_and_messages"
down_revision = "0004_create_user_tenants_table"
branch_labels = None
depends_on = None



def _ensure_chat_role_enum() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'chat_role_enum' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE chat_role_enum AS ENUM ('system', 'user', 'assistant', 'tool');
            END IF;
        END$$;
        """
    )


CHAT_ROLE_ENUM = postgresql.ENUM(
    "system",
    "user",
    "assistant",
    "tool",
    name="chat_role_enum",
    create_type=False,
)


def upgrade() -> None:
    _ensure_chat_role_enum()

    op.create_table(
        "chats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chats_tenant_id", "chats", ["tenant_id"])
    op.create_index("ix_chats_tenant_created", "chats", ["tenant_id", "created_at"])
    op.create_index("ix_chats_tenant_owner", "chats", ["tenant_id", "owner_id"])
    op.create_index("ix_chats_tenant_name", "chats", ["tenant_id", "name"])

    op.create_table(
        "chatmessages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", CHAT_ROLE_ENUM, nullable=False),
        sa.Column("content", postgresql.JSONB, nullable=False),
        sa.Column("message_type", sa.String(length=50), nullable=False, server_default="text"),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("meta", postgresql.JSONB, nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chatmessages_chat_id_created_at", "chatmessages", ["chat_id", "created_at"])
    op.create_index("ix_chatmessages_tenant_id", "chatmessages", ["tenant_id"])
    op.create_index("ix_chatmessages_tenant_created", "chatmessages", ["tenant_id", "created_at"])
    op.create_index("ix_chatmessages_tenant_chat", "chatmessages", ["tenant_id", "chat_id"])
    op.create_index("ix_chatmessages_message_type", "chatmessages", ["message_type"])


def downgrade() -> None:
    op.drop_index("ix_chatmessages_message_type", table_name="chatmessages")
    op.drop_index("ix_chatmessages_tenant_chat", table_name="chatmessages")
    op.drop_index("ix_chatmessages_tenant_created", table_name="chatmessages")
    op.drop_index("ix_chatmessages_tenant_id", table_name="chatmessages")
    op.drop_index("ix_chatmessages_chat_id_created_at", table_name="chatmessages")
    op.drop_table("chatmessages")

    op.drop_index("ix_chats_tenant_name", table_name="chats")
    op.drop_index("ix_chats_tenant_owner", table_name="chats")
    op.drop_index("ix_chats_tenant_created", table_name="chats")
    op.drop_index("ix_chats_tenant_id", table_name="chats")
    op.drop_table("chats")

    op.execute("DROP TYPE IF EXISTS chat_role_enum")
