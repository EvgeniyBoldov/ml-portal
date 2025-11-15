"""Add composite indexes for rag statuses and events outbox"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0015_add_additional_indexes"
down_revision = "0014_ensure_default_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_rag_statuses_doc_type_key",
        "rag_statuses",
        ["doc_id", "node_type", "node_key"],
    )
    op.create_index(
        "ix_events_outbox_delivered_created",
        "events_outbox",
        ["delivered_at", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_events_outbox_delivered_created", table_name="events_outbox")
    op.drop_index("ix_rag_statuses_doc_type_key", table_name="rag_statuses")
