"""Make document memory snapshots and entity bindings identity-safe.

Revision ID: 0135
Revises: 0134
"""
from __future__ import annotations

from alembic import op


revision = "0135"
down_revision = "0134"
branch_labels = None
depends_on = None

_ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    # 0134 used a regular unique constraint with a nullable project_id.
    # Merge any duplicate company bindings before replacing it with the
    # NULL-safe expression index.  Sources have no dependants, and aliases /
    # evidence are preserved on the surviving row.
    op.execute("""
        WITH duplicate_groups AS (
            SELECT entity_id, document_id, canonical_checksum, project_id,
                   (array_agg(id ORDER BY updated_at DESC, id DESC))[1] AS keeper_id,
                   array_agg(id) AS source_ids
            FROM knowledge_entity_sources
            GROUP BY entity_id, document_id, canonical_checksum, project_id
            HAVING count(*) > 1
        ), merged AS (
            SELECT groups.keeper_id,
                   ARRAY(
                       SELECT DISTINCT alias
                       FROM knowledge_entity_sources source
                       CROSS JOIN LATERAL unnest(source.aliases) AS alias
                       WHERE source.id = ANY(groups.source_ids)
                   ) AS aliases,
                   COALESCE((
                       SELECT jsonb_agg(DISTINCT section_id)
                       FROM knowledge_entity_sources source
                       CROSS JOIN LATERAL jsonb_array_elements_text(
                           COALESCE(source.evidence_section_ids, '[]'::jsonb)
                       ) AS section_id
                       WHERE source.id = ANY(groups.source_ids)
                   ), '[]'::jsonb) AS evidence_section_ids
            FROM duplicate_groups groups
        )
        UPDATE knowledge_entity_sources source
        SET aliases = COALESCE(merged.aliases, '{}'::varchar[]),
            evidence_section_ids = merged.evidence_section_ids
        FROM merged
        WHERE source.id = merged.keeper_id
    """)
    op.execute("""
        WITH duplicate_groups AS (
            SELECT entity_id, document_id, canonical_checksum, project_id,
                   (array_agg(id ORDER BY updated_at DESC, id DESC))[1] AS keeper_id,
                   array_agg(id) AS source_ids
            FROM knowledge_entity_sources
            GROUP BY entity_id, document_id, canonical_checksum, project_id
            HAVING count(*) > 1
        )
        DELETE FROM knowledge_entity_sources source
        USING duplicate_groups groups
        WHERE source.id = ANY(groups.source_ids) AND source.id <> groups.keeper_id
    """)
    op.drop_constraint("uq_knowledge_entity_sources_document", "knowledge_entity_sources", type_="unique")
    op.execute(f"""
        CREATE UNIQUE INDEX uq_knowledge_entity_sources_document
        ON knowledge_entity_sources (
            entity_id, document_id, canonical_checksum,
            COALESCE(project_id, '{_ZERO_UUID}'::uuid)
        )
    """)


def downgrade() -> None:
    op.drop_index("uq_knowledge_entity_sources_document", table_name="knowledge_entity_sources")
    op.create_unique_constraint(
        "uq_knowledge_entity_sources_document", "knowledge_entity_sources",
        ["entity_id", "document_id", "canonical_checksum", "project_id"],
    )
