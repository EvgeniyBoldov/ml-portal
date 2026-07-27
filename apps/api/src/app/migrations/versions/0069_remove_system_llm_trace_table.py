"""Remove the obsolete system LLM trace table.

Runtime LLM observability is owned by ``runtime_execution_events``. Existing
system trace rows are intentionally discarded; this is schema cleanup only,
with no historical backfill.
"""

from alembic import op


revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS system_llm_traces CASCADE")


def downgrade() -> None:
    raise RuntimeError("legacy system LLM trace removal is irreversible")
