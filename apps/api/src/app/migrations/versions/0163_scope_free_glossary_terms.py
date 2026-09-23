"""Unify lexical terms across source tenants and applicability scopes.

Revision ID: 0163
Revises: 0162
"""
from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
from alembic import op


revision = "0163"
down_revision = "0162"
branch_labels = None
depends_on = None


def _normalize(value: str) -> str:
    return " ".join(value.strip().casefold().split())[:200]


def _aliases(values: object, canonical: str) -> list[str]:
    seen = {_normalize(canonical)}
    result: list[str] = []
    for raw in values if isinstance(values, list) else []:
        value = " ".join(str(raw).split())[:255]
        key = _normalize(value)
        if key and key not in seen:
            result.append(value)
            seen.add(key)
    return result


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("""
        SELECT id, canonical_term, normalized_term, aliases
        FROM glossary_terms ORDER BY created_at, id
    """)).mappings().all()
    owners: dict[str, dict] = {}
    for row in rows:
        key = _normalize(row["canonical_term"])
        if key not in owners:
            owners[key] = {"id": row["id"], "canonical": row["canonical_term"], "aliases": _aliases(row["aliases"], row["canonical_term"])}
            continue
        owner = owners[key]
        owner["aliases"] = _aliases([*owner["aliases"], *(row["aliases"] or [])], owner["canonical"])
        connection.execute(sa.text("UPDATE glossary_meanings SET term_id = :owner WHERE term_id = :duplicate"),
                           {"owner": owner["id"], "duplicate": row["id"]})
        connection.execute(sa.text("DELETE FROM glossary_terms WHERE id = :id"), {"id": row["id"]})

    # Old scoped entries remain in their original tables for audit and for
    # the separate conversational-fact pipeline. Only their spellings move.
    legacy = connection.execute(sa.text("""
        SELECT canonical_term, aliases FROM glossary_entries
        WHERE is_active = true AND scope IN ('global', 'tenant', 'project')
        ORDER BY created_at, id
    """)).mappings().all()
    for row in legacy:
        key = _normalize(row["canonical_term"])
        if not key:
            continue
        if key not in owners:
            owners[key] = {"id": uuid.uuid4(), "canonical": row["canonical_term"], "aliases": []}
            connection.execute(sa.text("""
                INSERT INTO glossary_terms (id, canonical_term, normalized_term, aliases, created_at, updated_at)
                VALUES (:id, :canonical, :normalized, '[]'::jsonb, now(), now())
            """), {"id": owners[key]["id"], "canonical": row["canonical_term"], "normalized": key})
        owner = owners[key]
        owner["aliases"] = _aliases([*owner["aliases"], *(row["aliases"] or [])], owner["canonical"])

    for key, owner in owners.items():
        connection.execute(sa.text("""
            UPDATE glossary_terms SET normalized_term = :normalized,
                aliases = CAST(:aliases AS jsonb), updated_at = now()
            WHERE id = :id
        """), {"normalized": key, "aliases": json.dumps(owner["aliases"], ensure_ascii=False), "id": owner["id"]})

    op.drop_index("uq_glossary_terms_normalized_visibility", table_name="glossary_terms")
    op.drop_index("ix_glossary_terms_visibility_tenant_id", table_name="glossary_terms")
    op.drop_column("glossary_terms", "visibility_tenant_id")
    op.drop_column("glossary_terms", "entity_type")
    op.drop_column("glossary_terms", "entity_id")
    op.create_unique_constraint("uq_glossary_terms_normalized", "glossary_terms", ["normalized_term"])

    # Replace the seeded obsolete term contract while preserving any operator
    # edits around it. Runtime also appends the invariant for custom prompts.
    connection.execute(sa.text("""
        UPDATE system_llm_roles
        SET extras = jsonb_set(extras, '{document_memory_study_prompt}',
            to_jsonb(replace(extras->>'document_memory_study_prompt',
                'Термин должен иметь content.definition.',
                'term содержит только название и aliases; определение — отдельный description.'))),
            updated_at = now()
        WHERE role_type = 'document_memory_extractor'
          AND extras->>'document_memory_study_prompt' LIKE '%Термин должен иметь content.definition.%'
    """))


def downgrade() -> None:
    op.drop_constraint("uq_glossary_terms_normalized", "glossary_terms", type_="unique")
    op.add_column("glossary_terms", sa.Column("visibility_tenant_id", sa.UUID(), nullable=True))
    op.add_column("glossary_terms", sa.Column("entity_type", sa.String(length=64), nullable=False, server_default="term"))
    op.add_column("glossary_terms", sa.Column("entity_id", sa.String(length=255), nullable=True))
    op.create_foreign_key("fk_glossary_terms_visibility_tenant_id_tenants", "glossary_terms", "tenants", ["visibility_tenant_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_glossary_terms_visibility_tenant_id", "glossary_terms", ["visibility_tenant_id"])
    op.create_index("uq_glossary_terms_normalized_visibility", "glossary_terms",
                    ["normalized_term", sa.text("COALESCE(visibility_tenant_id, '00000000-0000-0000-0000-000000000000'::uuid)")], unique=True)
