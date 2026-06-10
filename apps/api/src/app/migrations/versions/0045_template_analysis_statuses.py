"""Add template analysis statuses table.

Revision ID: 0045
Revises: 0044
Create Date: 2026-06-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "template_analysis_statuses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("collections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_key", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("celery_task_id", sa.String(length=50), nullable=True),
        sa.Column("error_short", sa.Text(), nullable=True),
        sa.Column("metrics_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("row_id", "node_key", name="uq_template_analysis_statuses_row_node"),
    )
    op.create_index("ix_template_analysis_statuses_collection_id", "template_analysis_statuses", ["collection_id"], unique=False)
    op.create_index("ix_template_analysis_statuses_row_id", "template_analysis_statuses", ["row_id"], unique=False)
    op.create_index("ix_template_analysis_statuses_status", "template_analysis_statuses", ["status"], unique=False)
    op.create_index("ix_template_analysis_statuses_updated_at", "template_analysis_statuses", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_template_analysis_statuses_updated_at", table_name="template_analysis_statuses")
    op.drop_index("ix_template_analysis_statuses_status", table_name="template_analysis_statuses")
    op.drop_index("ix_template_analysis_statuses_row_id", table_name="template_analysis_statuses")
    op.drop_index("ix_template_analysis_statuses_collection_id", table_name="template_analysis_statuses")
    op.drop_table("template_analysis_statuses")
