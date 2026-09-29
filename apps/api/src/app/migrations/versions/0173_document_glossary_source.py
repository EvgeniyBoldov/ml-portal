"""Bind published glossary definitions to approved global document evidence."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0173"
down_revision = "0172"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("glossary_terms", sa.Column("approved_candidate_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_glossary_terms_approved_candidate", "glossary_terms", "memory_extraction_candidates",
        ["approved_candidate_id"], ["id"], ondelete="CASCADE",
    )
    op.create_index("ix_glossary_terms_approved_candidate_id", "glossary_terms", ["approved_candidate_id"])
    connection = op.get_bind()
    connection.execute(sa.text("""
        WITH source_candidates AS (
            SELECT term.id AS term_id, candidate.id AS candidate_id,
                   btrim(candidate.content->>'definition') AS definition,
                   candidate.updated_at
            FROM glossary_terms AS term
            JOIN memory_extraction_candidates AS candidate
              ON candidate.normalized_subject = term.normalized_term
            JOIN document_memory_snapshots AS snapshot ON snapshot.id = candidate.snapshot_id
            JOIN ragdocuments AS document ON document.id = snapshot.document_id
            WHERE candidate.candidate_type = 'term'
              AND candidate.resolution_status = 'resolved'
              AND document.scope = 'global'
              AND document.status <> 'archived'
              AND snapshot.status NOT IN ('superseded', 'failed', 'rejected')
              AND NOT EXISTS (
                  SELECT 1 FROM document_memory_snapshots newer
                  WHERE newer.document_id = snapshot.document_id
                    AND newer.created_at > snapshot.created_at
              )
              AND jsonb_array_length(candidate.evidence_section_ids) > 0
              AND btrim(candidate.content->>'definition') <> ''
        ), unambiguous AS (
            SELECT term_id FROM source_candidates
            GROUP BY term_id
            HAVING count(DISTINCT lower(definition)) = 1
        ), matching AS (
            SELECT source_candidates.*,
                   row_number() OVER (PARTITION BY term_id ORDER BY updated_at DESC, candidate_id DESC) AS ordinal
            FROM source_candidates
            JOIN unambiguous USING (term_id)
        )
        UPDATE glossary_terms AS term
        SET approved_candidate_id = matching.candidate_id,
            definition = matching.definition,
            is_active = true
        FROM matching
        WHERE matching.term_id = term.id AND matching.ordinal = 1
    """))
    connection.execute(sa.text("""
        UPDATE memory_extraction_candidates AS candidate
        SET visibility_tenant_id = NULL
        FROM glossary_terms AS term
        WHERE term.approved_candidate_id = candidate.id
    """))
    # Chat bindings are derived hints and reference IDs from the retired
    # glossary table. Rebuild them from the published catalogue on later turns.
    connection.execute(sa.text("DELETE FROM chat_memory_items WHERE kind = 'term_binding'"))
    connection.execute(sa.text("DELETE FROM facts WHERE kind = 'glossary'"))
    connection.execute(sa.text("DELETE FROM memory_items WHERE item_type = 'term'"))
    op.drop_table("glossary_meaning_sources")
    op.drop_table("glossary_meaning_project_bindings")
    op.drop_table("glossary_meanings")
    op.drop_table("glossary_observations")
    op.drop_table("glossary_entries")
    connection.execute(sa.text("DELETE FROM glossary_terms WHERE approved_candidate_id IS NULL"))
    op.alter_column("glossary_terms", "definition", nullable=False)
    op.alter_column("glossary_terms", "approved_candidate_id", nullable=False)
    connection.execute(sa.text("""
        UPDATE system_llm_roles SET
          rules = replace(replace(rules,
            'kind только fact или glossary.', 'kind только fact.'),
            'Для терминов и аббревиатур используй glossary: subject — канонический термин, value — краткое определение, aliases — только явно встречающиеся варианты.',
            'Термины и определения публикуются только после изучения документа и review.'),
          output_requirements = replace(output_requirements,
            'confidence и aliases используй только по schema.', 'confidence используй только по schema.'),
          safety = replace(safety,
            'Не публикуй project/company glossary: это делает только source-aware document ingestion.',
            'Термины и определения публикуются только после изучения глобального документа и review.')
        WHERE role_type = 'fact_extractor'
    """))
    connection.execute(sa.text("""
        UPDATE system_llm_roles SET
          mission = replace(mission, 'user, tenant и glossary-кандидаты', 'user и tenant facts'),
          rules = replace(rules,
            'Для glossary нормализуй термин и алиасы, не меняя смысл.',
            'Термины и определения принадлежат документному глоссарию.')
        WHERE role_type = 'fact_compactor'
    """))
    connection.execute(sa.text("""
        UPDATE system_llm_roles SET rules = replace(rules,
          'memory_candidates добавляй только для явно сформулированных пользователем устойчивых фактов или терминов;',
          'memory_candidates добавляй только для явно сформулированных пользователем устойчивых user/tenant фактов;')
        WHERE role_type = 'turn_preflight'
    """))
    connection.execute(sa.text("""
        UPDATE system_llm_roles SET
          mission = replace(mission, 'каталога проектов и доступного glossary', 'каталога проектов и semantic memory'),
          rules = replace(replace(rules,
            'facts, projects, glossary и semantic_memory', 'facts, projects и semantic_memory'),
            'Выбирай не более 12 фактов, 3 проектов, 6 терминов и 12 memory items.',
            'Выбирай не более 12 фактов, 3 проектов и 12 memory items.'),
          output_requirements = replace(output_requirements, 'glossary_indexes, ', '')
        WHERE role_type = 'memory'
    """))
    connection.execute(sa.text("""
        UPDATE system_llm_roles SET
          mission = 'Извлеки подтверждённые документом кандидаты в теневую память для проверки человеком.',
          rules = 'Используй только переданный документ, секции, каталоги и ledger. Каждый item ссылается на evidence_section_ids текущего batch. term содержит content.definition и создаётся только для document.access_scope=global. Остальные типы несут собственную применимость; не публикуй кандидаты самостоятельно.',
          output_requirements = 'Верни JSON по schema: items[] с candidate_type, subject, content, operation, scope_candidate, evidence_section_ids и применимыми полями связей. Для term обязателен content.definition.'
        WHERE role_type = 'document_memory_extractor'
    """))
    connection.execute(sa.text("""
        UPDATE system_llm_roles SET examples = NULL
        WHERE role_type IN ('memory', 'document_memory_extractor')
          AND (examples::text LIKE '%glossary_indexes%' OR examples::text LIKE '%term_kind%')
    """))


def downgrade() -> None:
    raise NotImplementedError("Retired glossary tables cannot be restored without archived data")
