"""Create rag_statuses table"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0011_create_rag_statuses_table"
down_revision = "0010_create_emb_status_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rag_statuses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("doc_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_type", sa.String(length=20), nullable=False),
        sa.Column("node_key", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=True),
        sa.Column("modality", sa.String(length=20), nullable=True),
        sa.Column("error_short", sa.Text(), nullable=True),
        sa.Column("metrics_json", postgresql.JSONB, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["doc_id"], ["ragdocuments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("doc_id", "node_type", "node_key", name="uq_rag_statuses_doc_node"),
    )
    op.create_index("ix_rag_statuses_doc_id", "rag_statuses", ["doc_id"])
    op.create_index("ix_rag_statuses_status", "rag_statuses", ["status"])
    op.create_index("ix_rag_statuses_node_type", "rag_statuses", ["node_type"])
    op.create_index("ix_rag_statuses_updated_at", "rag_statuses", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_rag_statuses_updated_at", table_name="rag_statuses")
    op.drop_index("ix_rag_statuses_node_type", table_name="rag_statuses")
    op.drop_index("ix_rag_statuses_status", table_name="rag_statuses")
    op.drop_index("ix_rag_statuses_doc_id", table_name="rag_statuses")
    op.drop_table("rag_statuses")
