"""Keep different applicability expressions in separate memory identities.

Revision ID: 0165
Revises: 0164
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0165"
down_revision = "0164"
branch_labels = None
depends_on = None


_PROJECT = "COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::uuid)"


def upgrade() -> None:
    op.add_column("memory_items", sa.Column("scope_signature", sa.String(80), nullable=False, server_default="legacy"))
    op.add_column("memory_claims", sa.Column("scope_signature", sa.String(80), nullable=False, server_default="legacy"))
    op.drop_index("uq_memory_items_identity", table_name="memory_items")
    op.create_index("uq_memory_items_identity", "memory_items",
                    ["scope", "item_type", sa.text(_PROJECT), "normalized_subject", "scope_signature"], unique=True)
    op.drop_index("uq_memory_claim_source_identity", table_name="memory_claims")
    op.create_index("uq_memory_claim_source_identity", "memory_claims",
                    ["document_id", "canonical_checksum", "scope", "item_type", sa.text(_PROJECT),
                     "normalized_subject", "scope_signature"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_memory_claim_source_identity", table_name="memory_claims")
    op.create_index("uq_memory_claim_source_identity", "memory_claims",
                    ["document_id", "canonical_checksum", "scope", "item_type", sa.text(_PROJECT),
                     "normalized_subject"], unique=True)
    op.drop_index("uq_memory_items_identity", table_name="memory_items")
    op.create_index("uq_memory_items_identity", "memory_items",
                    ["scope", "item_type", sa.text(_PROJECT), "normalized_subject"], unique=True)
    op.drop_column("memory_claims", "scope_signature")
    op.drop_column("memory_items", "scope_signature")
