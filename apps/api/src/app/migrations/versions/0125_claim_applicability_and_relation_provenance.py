"""Move applicability to claims and bind relations to their source."""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0125"
down_revision = "0124"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("memory_claims", sa.Column("applicability", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("memory_relations", sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_memory_relations_document", "memory_relations", "ragdocuments", ["document_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_memory_relations_document", "memory_relations", ["document_id"])
    # Existing relations predate provenance and cannot be safely attributed to
    # a source. They are derived data and will be recreated by ingestion.
    op.execute(sa.text("DELETE FROM memory_relations"))
    op.drop_index("uq_memory_relations_edge", table_name="memory_relations")
    op.create_index(
        "uq_memory_relations_edge", "memory_relations",
        ["memory_item_id", "document_id", "relation_type", "target_type", "target_id"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_memory_relations_edge", table_name="memory_relations")
    op.create_index(
        "uq_memory_relations_edge", "memory_relations",
        ["memory_item_id", "relation_type", "target_type", "target_id"], unique=True,
    )
    op.drop_index("ix_memory_relations_document", table_name="memory_relations")
    op.drop_constraint("fk_memory_relations_document", "memory_relations", type_="foreignkey")
    op.drop_column("memory_relations", "document_id")
    op.drop_column("memory_claims", "applicability")
