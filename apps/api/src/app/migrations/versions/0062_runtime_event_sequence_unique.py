"""Enforce one canonical sequence value per runtime run."""
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_runtime_execution_event_run_sequence",
        "runtime_execution_events",
        ["run_id", "sequence"],
    )


def downgrade() -> None:
    raise RuntimeError("runtime observability schema is irreversible")
