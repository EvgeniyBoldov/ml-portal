"""Persist task-local document memory and explicit continuation identity."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0193"
down_revision = "0192"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runtime_plan_tasks", sa.Column("continuation_of", sa.String(255), nullable=True))
    op.add_column("runtime_plan_tasks", sa.Column("memory_context", postgresql.JSONB(),
                                               nullable=True, server_default=sa.text("'[]'::jsonb")))


def downgrade() -> None:
    op.drop_column("runtime_plan_tasks", "memory_context")
    op.drop_column("runtime_plan_tasks", "continuation_of")
