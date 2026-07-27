"""Remove deprecated sandbox step storage.

The canonical runtime journal is runtime_execution_events.
"""
from alembic import op

revision = "0064_drop_sandbox_run_steps"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("sandbox_run_steps")


def downgrade() -> None:
    # Legacy trace storage is intentionally not restored.
    pass
