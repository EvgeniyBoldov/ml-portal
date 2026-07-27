"""Reconcile canonical runtime journal columns on databases stamped at 0064.

Some environments reached the 0064 revision while the 0063 schema delta was
not applied. This revision is schema-only and brings those installations to
the canonical runtime event shape without rewriting event data.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0065"
down_revision = "0064_drop_sandbox_run_steps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("runtime_execution_events")}
    uuid = postgresql.UUID(as_uuid=True)

    if "tenant_id" not in columns:
        op.add_column("runtime_execution_events", sa.Column("tenant_id", uuid, nullable=True))
    if "user_id" not in columns:
        op.add_column("runtime_execution_events", sa.Column("user_id", uuid, nullable=True))
    if "chat_id" not in columns:
        op.add_column("runtime_execution_events", sa.Column("chat_id", uuid, nullable=True))
    if "origin" not in columns:
        op.add_column(
            "runtime_execution_events",
            sa.Column("origin", sa.String(20), nullable=False, server_default="chat"),
        )
    if "duration_ms" not in columns:
        op.add_column("runtime_execution_events", sa.Column("duration_ms", sa.Integer(), nullable=True))

    indexes = {index["name"] for index in inspector.get_indexes("runtime_execution_events")}
    if "ix_runtime_execution_events_tenant_occurred" not in indexes:
        op.create_index(
            "ix_runtime_execution_events_tenant_occurred",
            "runtime_execution_events",
            ["tenant_id", "occurred_at"],
        )
    if "ix_runtime_execution_events_entity_id" not in indexes:
        op.create_index(
            "ix_runtime_execution_events_entity_id",
            "runtime_execution_events",
            ["entity_id"],
        )
    if "ix_runtime_execution_events_payload_gin" not in indexes:
        op.create_index(
            "ix_runtime_execution_events_payload_gin",
            "runtime_execution_events",
            ["payload"],
            postgresql_using="gin",
        )


def downgrade() -> None:
    raise RuntimeError("runtime event journal reconciliation is irreversible")
