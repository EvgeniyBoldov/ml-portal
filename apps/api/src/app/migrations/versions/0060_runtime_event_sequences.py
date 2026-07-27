"""Serialize per-run runtime event sequence allocation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The table is part of the atomic observability-core schema in 0059.
    # Keep this revision as a no-op for databases that already applied it;
    # a fresh upgrade must not attempt to create the table twice.
    pass


def downgrade() -> None:
    raise RuntimeError("runtime event sequence storage is irreversible")
