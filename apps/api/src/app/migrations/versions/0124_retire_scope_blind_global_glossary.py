"""Withdraw legacy global terms without source-scope provenance.

Revision ID: 0124
Revises: 0123
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0124"
down_revision = "0123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Earlier turn-memory extraction promoted collection search results to
    # global glossary without preserving the source document scope.  They
    # cannot be safely shared, so source-aware document ingestion will rebuild
    # them when appropriate.
    op.execute(sa.text("""
        UPDATE glossary_entries entry
        SET is_active = false, status = 'unconfirmed', updated_at = now()
        WHERE entry.scope = 'global'
          AND EXISTS (
              SELECT 1 FROM glossary_observations observation
              WHERE observation.entry_id = entry.id
                AND observation.source_type = 'tool_result'
          )
          AND NOT EXISTS (
              SELECT 1 FROM glossary_observations observation
              WHERE observation.entry_id = entry.id
                AND observation.source_type = 'document'
          )
    """))


def downgrade() -> None:
    pass
