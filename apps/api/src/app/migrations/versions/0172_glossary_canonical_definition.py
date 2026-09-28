"""Require an approved definition for active glossary terms.

Legacy definitions are copied only when all approved sources agree. Ambiguous
and undefined terms remain available for administrator repair, but unpublished.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0172"
down_revision = "0171"
branch_labels = None
depends_on = None


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def upgrade() -> None:
    op.add_column("glossary_terms", sa.Column("definition", sa.Text(), nullable=True))
    connection = op.get_bind()
    terms = connection.execute(sa.text("SELECT id, canonical_term, normalized_term FROM glossary_terms")).mappings().all()
    meanings = connection.execute(sa.text("""
        SELECT term_id, definition FROM glossary_meanings
        WHERE resolution_status = 'resolved'
    """)).mappings().all()
    legacy = connection.execute(sa.text("""
        SELECT canonical_term, description FROM glossary_entries
        WHERE is_active = true AND status = 'confirmed'
          AND scope IN ('global', 'tenant', 'project')
    """)).mappings().all()
    by_id: dict[object, list[str]] = {}
    by_name: dict[str, list[str]] = {}
    for row in meanings:
        by_id.setdefault(row["term_id"], []).append(_clean(row["definition"]))
    for row in legacy:
        key = _clean(row["canonical_term"]).casefold()
        by_name.setdefault(key, []).append(_clean(row["description"]))
    for term in terms:
        values = [value for value in [*by_id.get(term["id"], []), *by_name.get(term["normalized_term"], [])]
                  if value and value.casefold() != _clean(term["canonical_term"]).casefold()]
        definitions = {value.casefold(): value for value in values}
        if len(definitions) == 1:
            connection.execute(sa.text("UPDATE glossary_terms SET definition = :definition WHERE id = :id"),
                               {"definition": next(iter(definitions.values())), "id": term["id"]})
        else:
            connection.execute(sa.text("UPDATE glossary_terms SET is_active = false WHERE id = :id"),
                               {"id": term["id"]})
    op.create_check_constraint("ck_glossary_active_definition", "glossary_terms",
                               "NOT is_active OR (definition IS NOT NULL AND btrim(definition) <> '')")
    # Correct the seeded operator prompt without overwriting independent edits.
    connection.execute(sa.text("""
        UPDATE system_llm_roles
        SET extras = jsonb_set(extras, '{document_memory_study_prompt}',
            to_jsonb(replace(extras->>'document_memory_study_prompt',
                'term содержит только название и aliases; определение — отдельный description.',
                'term содержит название, aliases и content.definition; без определения term не создавай. Не дублируй определение отдельным description.'))),
            updated_at = now()
        WHERE role_type = 'document_memory_extractor'
          AND extras->>'document_memory_study_prompt' LIKE '%определение — отдельный description.%'
    """))


def downgrade() -> None:
    op.drop_constraint("ck_glossary_active_definition", "glossary_terms", type_="check")
    op.drop_column("glossary_terms", "definition")
