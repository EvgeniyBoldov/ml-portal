from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20250904_213024"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Enums
    role_enum = sa.Enum("admin", "editor", "reader", name="role_enum")
    chat_role_enum = sa.Enum("system", "user", "assistant", "tool", name="chat_role_enum")
    rag_status_enum = sa.Enum("uploaded", "normalizing", "chunking", "embedding", "indexing", "ready", "archived", "deleting", "error", name="rag_status_enum")
    analyze_status_enum = sa.Enum("queued", "processing", "done", "error", "canceled", name="analyze_status_enum")
    role_enum.create(op.get_bind(), checkfirst=True)
    chat_role_enum.create(op.get_bind(), checkfirst=True)
    rag_status_enum.create(op.get_bind(), checkfirst=True)
    analyze_status_enum.create(op.get_bind(), checkfirst=True)

    # users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fio", sa.Text(), nullable=True),
        sa.Column("login", sa.String(length=255), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", role_enum, nullable=False, server_default="reader"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # user_tokens (PAT)
    op.create_table(
        "usertokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # user_refresh_tokens
    op.create_table(
        "userrefreshtokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refresh_hash", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rotating", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("refresh_hash", name="uq_user_refresh_tokens_refresh_hash"),
    )
    op.create_index("ix_userrefreshtokens_user_id_expires_at", "userrefreshtokens", ["user_id", "expires_at"])

    # chats
    op.create_table(
        "chats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
    )

    # chat_messages
    op.create_table(
        "chatmessages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", chat_role_enum, nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chatmessages_chat_id_created_at", "chatmessages", ["chat_id", "created_at"])

    # rag_documents
    op.create_table(
        "ragdocuments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", rag_status_enum, nullable=False, server_default="uploaded"),
        sa.Column("date_upload", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("url_file", sa.Text(), nullable=True),
        sa.Column("url_canonical_file", sa.Text(), nullable=True),
        sa.Column("source_mime", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # rag_chunks
    op.create_table(
        "ragchunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_idx", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("embedding_version", sa.String(length=255), nullable=True),
        sa.Column("date_embedding", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("qdrant_point_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["ragdocuments.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ragchunks_document_id_chunk_idx", "ragchunks", ["document_id", "chunk_idx"])

    # analysis_documents
    op.create_table(
        "analysisdocuments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", analyze_status_enum, nullable=False, server_default="queued"),
        sa.Column("date_upload", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("url_file", sa.Text(), nullable=True),
        sa.Column("url_canonical_file", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # analysis_chunks
    op.create_table(
        "analysischunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_idx", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("embedding_version", sa.String(length=255), nullable=True),
        sa.Column("date_embedding", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["analysisdocuments.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_analysischunks_document_id_chunk_idx", "analysischunks", ["document_id", "chunk_idx"])

def downgrade():
    op.drop_index("ix_analysischunks_document_id_chunk_idx", table_name="analysischunks")
    op.drop_table("analysischunks")
    op.drop_table("analysisdocuments")
    op.drop_index("ix_ragchunks_document_id_chunk_idx", table_name="ragchunks")
    op.drop_table("ragchunks")
    op.drop_table("ragdocuments")
    op.drop_index("ix_chatmessages_chat_id_created_at", table_name="chatmessages")
    op.drop_table("chatmessages")
    op.drop_table("chats")
    op.drop_index("ix_userrefreshtokens_user_id_expires_at", table_name="userrefreshtokens")
    op.drop_table("userrefreshtokens")
    op.drop_table("usertokens")
    op.drop_table("users")

    # drop enums
    op.execute("DROP TYPE IF EXISTS analyze_status_enum")
    op.execute("DROP TYPE IF EXISTS rag_status_enum")
    op.execute("DROP TYPE IF EXISTS chat_role_enum")
    op.execute("DROP TYPE IF EXISTS role_enum")
