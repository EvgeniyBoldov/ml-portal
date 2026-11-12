"""Preserve unknown source coverage as NULL."""
from alembic import op
import sqlalchemy as sa

revision = "tool_results_0005"
down_revision = "tool_results_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Earlier versions defaulted missing coverage metadata to true. Those
    # values cannot prove completeness, so retain explicit false and mark the
    # unsubstantiated true values unknown.
    op.alter_column("runtime_tool_payloads", "source_complete",
                    existing_type=sa.Boolean(), nullable=True,
                    existing_server_default=sa.true(), server_default=None)
    op.execute(sa.text("""
        UPDATE runtime_tool_payloads
        SET source_complete = NULL
        WHERE source_complete IS TRUE
          AND (dataset_meta IS NULL OR NOT (dataset_meta ? 'complete'))
    """))


def downgrade() -> None:
    op.execute(sa.text("UPDATE runtime_tool_payloads SET source_complete = FALSE WHERE source_complete IS NULL"))
    op.alter_column("runtime_tool_payloads", "source_complete",
                    existing_type=sa.Boolean(), nullable=False,
                    server_default=sa.true())
