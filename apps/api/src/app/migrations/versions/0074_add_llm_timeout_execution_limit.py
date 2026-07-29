"""Add the scoped per-call LLM timeout to execution limits."""

import sqlalchemy as sa
from alembic import op


revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("execution_limits", sa.Column("llm_timeout_s", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("execution_limits", "llm_timeout_s")
