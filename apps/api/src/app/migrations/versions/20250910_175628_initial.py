# app/migrations/versions/20250910_175628_initial.py
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20250910_175628_initial"
down_revision = "20250908_154500_add_tokens"
branch_labels = None
depends_on = None

def upgrade():
    # Use string columns instead of ENUMs to avoid conflicts
    # ENUMs will be handled by SQLAlchemy models

    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("login", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default=sa.text("'reader'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_users_login", "users", ["login"], unique=True)

    # --- user_tokens ---
    op.create_table(
        "user_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_tokens_user_id", "user_tokens", ["user_id"])

    # --- user_refresh_tokens ---
    op.create_table(
        "user_refresh_tokens",
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
    op.create_index("ix_user_refresh_tokens_user_id", "user_refresh_tokens", ["user_id"])

    # --- chats ---
    op.create_table(
        "chats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key("fk_chats_owner_id_users", "chats", "users", ["owner_id"], ["id"], ondelete="CASCADE")

    # --- chat messages ---
    op.create_table(
        "chatmessages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["chat_id"], ["chats.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_chatmessages_chat_id_created_at", "chatmessages", ["chat_id", "created_at"])

    # --- RAG documents ---
    op.create_table(
        "ragdocuments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'uploaded'")),
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
    op.create_foreign_key("fk_ragdocuments_uploaded_by_users", "ragdocuments", "users", ["uploaded_by"], ["id"], ondelete="SET NULL")

    # --- RAG chunks ---
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

    # --- Analysis documents ---
    op.create_table(
        "analysisdocuments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("date_upload", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("url_file", sa.Text(), nullable=True),
        sa.Column("url_canonical_file", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key("fk_analysisdocuments_uploaded_by_users", "analysisdocuments", "users", ["uploaded_by"], ["id"], ondelete="SET NULL")

    # --- Analysis chunks ---
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
    # Drop in reverse dependency order
    op.drop_index("ix_analysischunks_document_id_chunk_idx", table_name="analysischunks")
    op.drop_table("analysischunks")
    op.drop_constraint("fk_analysisdocuments_uploaded_by_users", "analysisdocuments", type_="foreignkey")
    op.drop_table("analysisdocuments")

    op.drop_index("ix_ragchunks_document_id_chunk_idx", table_name="ragchunks")
    op.drop_table("ragchunks")
    op.drop_constraint("fk_ragdocuments_uploaded_by_users", "ragdocuments", type_="foreignkey")
    op.drop_table("ragdocuments")

    op.drop_index("ix_chatmessages_chat_id_created_at", table_name="chatmessages")
    op.drop_table("chatmessages")
    op.drop_constraint("fk_chats_owner_id_users", "chats", type_="foreignkey")
    op.drop_table("chats")

    # Drop user-related tables
    op.drop_index("ix_user_refresh_tokens_user_id", table_name="user_refresh_tokens")
    op.drop_table("user_refresh_tokens")
    op.drop_index("ix_user_tokens_user_id", table_name="user_tokens")
    op.drop_table("user_tokens")
    op.drop_index("ix_users_login", table_name="users")
    op.drop_table("users")

    # ENUMs will be dropped automatically when tables are dropped
