"""Create chunks table for ingest pipeline"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0009_create_ingest_chunks"
down_revision = "0008_create_sources_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chunks",
        sa.Column("chunk_id", sa.Text(), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("offset", sa.Integer(), nullable=False),
        sa.Column("length", sa.Integer(), nullable=False),
        sa.Column("lang", sa.Text(), nullable=True),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column("meta", postgresql.JSONB, nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["sources.source_id"], ondelete="CASCADE"),
        sa.UniqueConstraint("source_id", "offset", name="uq_chunks_source_offset"),
    )
    op.create_index("ix_chunks_source_id", "chunks", ["source_id"])
    op.create_index("ix_chunks_hash", "chunks", ["hash"])


def downgrade() -> None:
    op.drop_index("ix_chunks_hash", table_name="chunks")
    op.drop_index("ix_chunks_source_id", table_name="chunks")
    op.drop_table("chunks")
