"""Make semantic-memory identities unique even when project_id is NULL.

Revision ID: 0119
Revises: 0118
"""
from __future__ import annotations

from alembic import op


revision = "0119"
down_revision = "0118"
branch_labels = None
depends_on = None

_ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    # PostgreSQL unique indexes treat NULL values as distinct.  Company items
    # and claims use NULL project_id, so use a stable sentinel in the index.
    op.execute(f"""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_memory_items_identity
        ON memory_items (scope, item_type,
            COALESCE(project_id, '{_ZERO_UUID}'::uuid), normalized_subject)
    """)
    op.drop_index("uq_memory_claim_source_identity", table_name="memory_claims")
    op.execute(f"""
        CREATE UNIQUE INDEX uq_memory_claim_source_identity
        ON memory_claims (document_id, canonical_checksum, scope, item_type,
            COALESCE(project_id, '{_ZERO_UUID}'::uuid), normalized_subject)
    """)


def downgrade() -> None:
    op.drop_index("uq_memory_claim_source_identity", table_name="memory_claims")
    op.create_index(
        "uq_memory_claim_source_identity", "memory_claims",
        ["document_id", "canonical_checksum", "scope", "item_type", "project_id", "normalized_subject"],
        unique=True,
    )
    op.drop_index("uq_memory_items_identity", table_name="memory_items")
