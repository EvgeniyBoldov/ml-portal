"""Create ragdocuments table"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0006_create_rag_documents"
down_revision = "0005_create_chats_and_messages"
branch_labels = None
depends_on = None


def _ensure_document_status_enum() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_type t
                JOIN pg_namespace n ON n.oid = t.typnamespace
                WHERE t.typname = 'documentstatus' AND n.nspname = 'public'
            ) THEN
                CREATE TYPE documentstatus AS ENUM (
                    'uploaded', 'uploading', 'processing', 'processed',
                    'ready', 'failed', 'archived', 'queued'
                );
            END IF;
        END$$;
        """
    )


DOCUMENT_STATUS_ENUM = postgresql.ENUM(
    "uploaded",
    "uploading",
    "processing",
    "processed",
    "ready",
    "failed",
    "archived",
    "queued",
    name="documentstatus",
    create_type=False,
)


def upgrade() -> None:
    _ensure_document_status_enum()

    op.create_table(
        "ragdocuments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", DOCUMENT_STATUS_ENUM, nullable=False, server_default="uploaded"),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="local"),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("source_mime", sa.String(length=255), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("s3_key_raw", sa.String(length=500), nullable=True),
        sa.Column("s3_key_processed", sa.String(length=500), nullable=True),
        sa.Column("url_file", sa.Text(), nullable=True),
        sa.Column("url_canonical_file", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("global_version", sa.Integer(), nullable=True),
        sa.Column("date_upload", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("agg_status", sa.String(length=20), nullable=True),
        sa.Column("agg_details_json", postgresql.JSONB, nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ragdocuments_tenant_id", "ragdocuments", ["tenant_id"])
    op.create_index("ix_ragdocuments_uploaded_by", "ragdocuments", ["uploaded_by"])
    op.create_index("ix_ragdocuments_status", "ragdocuments", ["status"])
    op.create_index("ix_ragdocuments_scope", "ragdocuments", ["scope"])


def downgrade() -> None:
    op.drop_index("ix_ragdocuments_scope", table_name="ragdocuments")
    op.drop_index("ix_ragdocuments_status", table_name="ragdocuments")
    op.drop_index("ix_ragdocuments_uploaded_by", table_name="ragdocuments")
    op.drop_index("ix_ragdocuments_tenant_id", table_name="ragdocuments")
    op.drop_table("ragdocuments")

    op.execute("DROP TYPE IF EXISTS documentstatus")
