"""Create ragchunks table"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0007_create_rag_chunks"
down_revision = "0006_create_rag_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ragchunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_idx", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("embedding_version", sa.String(length=255), nullable=True),
        sa.Column("date_embedding", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column("qdrant_point_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["ragdocuments.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ragchunks_document_id", "ragchunks", ["document_id"])
    op.create_index("ix_ragchunks_document_idx", "ragchunks", ["document_id", "chunk_idx"])


def downgrade() -> None:
    op.drop_index("ix_ragchunks_document_idx", table_name="ragchunks")
    op.drop_index("ix_ragchunks_document_id", table_name="ragchunks")
    op.drop_table("ragchunks")
