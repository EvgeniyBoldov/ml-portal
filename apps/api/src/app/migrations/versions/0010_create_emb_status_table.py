"""Create emb_status table"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0010_create_emb_status_table"
down_revision = "0009_create_ingest_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emb_status",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model_alias", sa.Text(), primary_key=True),
        sa.Column("done_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("model_version", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["source_id"], ["sources.source_id"], ondelete="CASCADE"),
    )
    op.create_index("ix_emb_status_source_id", "emb_status", ["source_id"])
    op.create_index("ix_emb_status_model_alias", "emb_status", ["model_alias"])


def downgrade() -> None:
    op.drop_index("ix_emb_status_model_alias", table_name="emb_status")
    op.drop_index("ix_emb_status_source_id", table_name="emb_status")
    op.drop_table("emb_status")
