"""Dataset metadata, revisions and idempotent source pages."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "tool_results_0003"
down_revision = "tool_results_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runtime_tool_payloads", sa.Column("dataset_meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("runtime_tool_payloads", sa.Column("arguments", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("runtime_tool_payloads", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.create_table("runtime_tool_result_pages",
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_key", sa.String(64), nullable=False),
        sa.Column("call_id", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("meta", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["result_id"], ["runtime_tool_payloads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("result_id", "page_key"))


def downgrade() -> None:
    op.drop_table("runtime_tool_result_pages")
    for column in ("revision", "arguments", "dataset_meta"):
        op.drop_column("runtime_tool_payloads", column)
