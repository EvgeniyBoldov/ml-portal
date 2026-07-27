"""Associate chat pause/resume with canonical runtime root runs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_turns", sa.Column("runtime_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_chat_turns_runtime_run_id", "chat_turns", ["runtime_run_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_turns_runtime_run_id", table_name="chat_turns")
    op.drop_column("chat_turns", "runtime_run_id")
