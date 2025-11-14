"""Create sources table"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0008_create_sources_table"
down_revision = "0007_create_rag_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sources",
        sa.Column("source_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
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
        sa.Column("meta", postgresql.JSONB, nullable=True),
        sa.CheckConstraint(
            "status IN ('uploaded','normalized','chunked','embedding','ready','failed','reindexing')",
            name="ck_sources_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sources_status", "sources", ["status"])
    op.create_index("ix_sources_updated_at", "sources", ["updated_at"])
    op.create_index("ix_sources_tenant_id", "sources", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_sources_tenant_id", table_name="sources")
    op.drop_index("ix_sources_updated_at", table_name="sources")
    op.drop_index("ix_sources_status", table_name="sources")
    op.drop_table("sources")
