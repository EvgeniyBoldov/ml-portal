"""Replace the observability event row with the canonical runtime journal."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This is intentionally destructive: historical traces are not part of
    # the new contract and no compatibility projection is retained.
    op.execute("TRUNCATE TABLE runtime_execution_events, runtime_event_sequences")
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column("runtime_execution_events", sa.Column("tenant_id", uuid, nullable=True))
    op.add_column("runtime_execution_events", sa.Column("user_id", uuid, nullable=True))
    op.add_column("runtime_execution_events", sa.Column("chat_id", uuid, nullable=True))
    op.add_column("runtime_execution_events", sa.Column("origin", sa.String(20), nullable=False, server_default="chat"))
    op.add_column("runtime_execution_events", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.create_index("ix_runtime_execution_events_tenant_occurred", "runtime_execution_events", ["tenant_id", "occurred_at"])
    op.create_index("ix_runtime_execution_events_entity_id", "runtime_execution_events", ["entity_id"])
    op.create_index("ix_runtime_execution_events_payload_gin", "runtime_execution_events", ["payload"], postgresql_using="gin")


def downgrade() -> None:
    raise RuntimeError("canonical runtime event journal is irreversible")
