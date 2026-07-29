"""Add the run-level parallel task limit.

The ORM model started reading this optional execution limit before the schema
change was recorded in Alembic.  Keep the operation idempotent so it also
works on environments where the column was temporarily added by hand.
"""

from alembic import op


revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE execution_limits "
        "ADD COLUMN IF NOT EXISTS max_parallel_tasks INTEGER"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE execution_limits "
        "DROP COLUMN IF EXISTS max_parallel_tasks"
    )
