"""Harden semantic-memory safety defaults and source lifecycle.

Revision ID: 0113
Revises: 0112
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0113"
down_revision = "0112"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Upgrade only the legacy bootstrap memory role. Operator-managed prompts
    # that already declare intent are left untouched.
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET output_requirements =
              'Верни JSON с fact_indexes, project_indexes, glossary_indexes, ambiguities и intent (informational, action или unknown). Каждый индекс обязан существовать во входе.',
            updated_at = now()
        WHERE role_type = 'memory'
          AND COALESCE(is_active, true)
          AND COALESCE(output_requirements, '') NOT ILIKE '%intent%'
    """))

    # Cascading removal of a RAG document also removes MemoryItemSource rows.
    # Preserve the memory item for audit, but make it non-authoritative once
    # its final source disappears.
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION mark_memory_item_stale_without_sources()
        RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM memory_item_sources
                WHERE memory_item_id = OLD.memory_item_id
            ) THEN
                UPDATE memory_items
                SET state = 'stale', updated_at = now()
                WHERE id = OLD.memory_item_id AND state = 'active';
            END IF;
            RETURN OLD;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_memory_item_source_delete_stales_item
        AFTER DELETE ON memory_item_sources
        FOR EACH ROW EXECUTE FUNCTION mark_memory_item_stale_without_sources();
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS trg_memory_item_source_delete_stales_item ON memory_item_sources"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS mark_memory_item_stale_without_sources()"))
