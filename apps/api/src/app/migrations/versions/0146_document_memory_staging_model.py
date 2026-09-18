"""Add canonical staging tables for document-derived memory.

Revision ID: 0146
Revises: 0145
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0146"
down_revision = "0145"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    jsonb = postgresql.JSONB()
    op.create_table(
        "document_memory_snapshots",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("document_id", uuid, sa.ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_checksum", sa.String(length=128), nullable=False),
        sa.Column("extractor_version", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="completed"),
        sa.Column("metrics", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("document_id", "canonical_checksum", name="uq_document_memory_snapshot_revision"),
        sa.CheckConstraint("status IN ('completed', 'failed', 'superseded')", name="ck_document_memory_snapshot_state"),
    )
    op.create_index("ix_document_memory_snapshots_document", "document_memory_snapshots", ["document_id", "created_at"])

    op.create_table(
        "memory_extraction_candidates",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("snapshot_id", uuid, sa.ForeignKey("document_memory_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("legacy_memory_item_id", uuid, sa.ForeignKey("memory_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("legacy_memory_claim_id", uuid, sa.ForeignKey("memory_claims.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("candidate_type", sa.String(length=32), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("normalized_subject", sa.String(length=200), nullable=False),
        sa.Column("content", jsonb, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("evidence_section_ids", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("aliases", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("related_entities", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("related_project_keys", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("extraction_confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("scope_candidate", sa.String(length=16), nullable=True),
        sa.Column("resolution_status", sa.String(length=16), nullable=False, server_default="extracted"),
        sa.Column("resolution_method", sa.String(length=32), nullable=True),
        sa.Column("resolution_rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("snapshot_id", "ordinal", name="uq_memory_candidate_snapshot_ordinal"),
        sa.UniqueConstraint("legacy_memory_claim_id", name="uq_memory_candidate_legacy_claim"),
        sa.CheckConstraint("candidate_type IN ('term', 'description', 'relationship', 'rule', 'constraint', 'procedure', 'decision')", name="ck_memory_candidate_type"),
        sa.CheckConstraint("scope_candidate IS NULL OR scope_candidate IN ('global', 'project', 'multi_project', 'unknown')", name="ck_memory_candidate_scope"),
        sa.CheckConstraint("resolution_status IN ('extracted', 'needs_review', 'resolved', 'rejected', 'stale')", name="ck_memory_candidate_resolution"),
        sa.CheckConstraint("resolution_method IS NULL OR resolution_method IN ('document_hint', 'exact_project_key', 'unique_alias', 'content_evidence', 'llm_suggestion', 'manual', 'migration')", name="ck_memory_candidate_resolution_method"),
        sa.CheckConstraint("extraction_confidence >= 0.0 AND extraction_confidence <= 1.0", name="ck_memory_candidate_confidence"),
    )
    op.create_index("ix_memory_candidates_resolution", "memory_extraction_candidates", ["resolution_status", "scope_candidate"])
    op.create_index("ix_memory_candidates_subject", "memory_extraction_candidates", ["candidate_type", "normalized_subject"])

    op.create_table(
        "memory_candidate_project_bindings",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("candidate_id", uuid, sa.ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="suggested"),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("candidate_id", "project_id", "role", name="uq_memory_candidate_project_binding"),
        sa.CheckConstraint("role IN ('applies_to', 'mentions')", name="ck_memory_candidate_project_binding_role"),
        sa.CheckConstraint("status IN ('suggested', 'confirmed', 'rejected')", name="ck_memory_candidate_project_binding_status"),
        sa.CheckConstraint("method IN ('document_hint', 'exact_project_key', 'unique_alias', 'content_evidence', 'llm_suggestion', 'manual', 'migration')", name="ck_memory_candidate_project_binding_method"),
        sa.CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_memory_candidate_project_binding_confidence"),
    )
    op.create_index("ix_memory_candidate_project_binding_project", "memory_candidate_project_bindings", ["project_id", "status"])

    op.create_table(
        "glossary_terms",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("canonical_term", sa.String(length=255), nullable=False),
        sa.Column("normalized_term", sa.String(length=255), nullable=False),
        sa.Column("aliases", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("entity_type", sa.String(length=64), nullable=False, server_default="term"),
        sa.Column("entity_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("normalized_term", name="uq_glossary_terms_normalized"),
    )
    op.create_table(
        "glossary_meanings",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("term_id", uuid, sa.ForeignKey("glossary_terms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", uuid, sa.ForeignKey("memory_extraction_candidates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("legacy_glossary_entry_id", uuid, sa.ForeignKey("glossary_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("scope_candidate", sa.String(length=16), nullable=False),
        sa.Column("resolution_status", sa.String(length=16), nullable=False, server_default="extracted"),
        sa.Column("resolution_method", sa.String(length=32), nullable=True),
        sa.Column("resolution_rationale", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("visibility_tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("legacy_glossary_entry_id", name="uq_glossary_meaning_legacy_entry"),
        sa.CheckConstraint("scope_candidate IN ('global', 'project', 'multi_project', 'unknown')", name="ck_glossary_meaning_scope"),
        sa.CheckConstraint("resolution_status IN ('extracted', 'needs_review', 'resolved', 'rejected', 'stale')", name="ck_glossary_meaning_resolution"),
        sa.CheckConstraint("resolution_method IS NULL OR resolution_method IN ('document_hint', 'exact_project_key', 'unique_alias', 'content_evidence', 'llm_suggestion', 'manual', 'migration')", name="ck_glossary_meaning_resolution_method"),
        sa.CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_glossary_meaning_confidence"),
    )
    op.create_index("ix_glossary_meanings_term_resolution", "glossary_meanings", ["term_id", "resolution_status"])
    op.create_table(
        "glossary_meaning_project_bindings",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("meaning_id", uuid, sa.ForeignKey("glossary_meanings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="suggested"),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("meaning_id", "project_id", name="uq_glossary_meaning_project_binding"),
        sa.CheckConstraint("status IN ('suggested', 'confirmed', 'rejected')", name="ck_glossary_meaning_project_binding_status"),
        sa.CheckConstraint("method IN ('document_hint', 'exact_project_key', 'unique_alias', 'content_evidence', 'llm_suggestion', 'manual', 'migration')", name="ck_glossary_meaning_project_binding_method"),
        sa.CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_glossary_meaning_project_binding_confidence"),
    )
    op.create_index("ix_glossary_meaning_project_binding_project", "glossary_meaning_project_bindings", ["project_id", "status"])
    op.create_table(
        "glossary_meaning_sources",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("meaning_id", uuid, sa.ForeignKey("glossary_meanings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", uuid, sa.ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=True),
        sa.Column("legacy_glossary_observation_id", uuid, sa.ForeignKey("glossary_observations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_id", uuid, sa.ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("visibility_tenant_id", uuid, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("evidence_section_ids", jsonb, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("meaning_id", "legacy_glossary_observation_id", name="uq_glossary_meaning_source_legacy_observation"),
        sa.UniqueConstraint("meaning_id", "candidate_id", name="uq_glossary_meaning_source_candidate"),
        sa.CheckConstraint("(candidate_id IS NOT NULL)::integer + (legacy_glossary_observation_id IS NOT NULL)::integer = 1", name="ck_glossary_meaning_source_origin"),
    )
    op.create_index("ix_glossary_meaning_sources_document", "glossary_meaning_sources", ["document_id"])

    # Backfill is additive. Current read paths continue to use the legacy
    # projection, while these rows make its source-level semantics inspectable.
    op.execute(sa.text("""
        INSERT INTO document_memory_snapshots (id, document_id, canonical_checksum, status, metrics, created_at, updated_at)
        SELECT gen_random_uuid(), claim.document_id, claim.canonical_checksum, 'completed',
               jsonb_build_object('backfilled_from', 'memory_claims'), now(), now()
        FROM memory_claims claim
        GROUP BY claim.document_id, claim.canonical_checksum
        ON CONFLICT (document_id, canonical_checksum) DO NOTHING
    """))
    op.execute(sa.text("""
        WITH ranked_claims AS (
            SELECT claim.*, item.subject,
                   row_number() OVER (PARTITION BY claim.document_id, claim.canonical_checksum ORDER BY claim.created_at, claim.id) - 1 AS ordinal
            FROM memory_claims claim
            JOIN memory_items item ON item.id = claim.memory_item_id
        )
        INSERT INTO memory_extraction_candidates (
            id, snapshot_id, legacy_memory_item_id, legacy_memory_claim_id, ordinal,
            candidate_type, subject, normalized_subject, content, content_text,
            evidence_section_ids, aliases, related_entities, related_project_keys,
            extraction_confidence, scope_candidate, resolution_status, resolution_method,
            resolution_rationale, created_at, updated_at
        )
        SELECT gen_random_uuid(), snapshot.id, ranked.memory_item_id, ranked.id, ranked.ordinal,
               ranked.item_type, ranked.subject, ranked.normalized_subject, ranked.content, ranked.content_text,
               ranked.evidence_section_ids, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
               ranked.extraction_confidence,
               CASE WHEN ranked.scope = 'company' THEN 'global' ELSE 'project' END,
               CASE ranked.state WHEN 'active' THEN 'resolved' WHEN 'stale' THEN 'stale' ELSE 'needs_review' END,
               'migration', 'Backfilled from the legacy published memory claim.', ranked.created_at, ranked.updated_at
        FROM ranked_claims ranked
        JOIN document_memory_snapshots snapshot
          ON snapshot.document_id = ranked.document_id AND snapshot.canonical_checksum = ranked.canonical_checksum
        ON CONFLICT (legacy_memory_claim_id) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO memory_candidate_project_bindings (
            id, candidate_id, project_id, role, status, method, confidence, rationale, created_at, updated_at
        )
        SELECT gen_random_uuid(), candidate.id, claim.project_id, 'applies_to', 'confirmed', 'migration',
               claim.project_resolution_confidence, 'Primary project from legacy claim.', now(), now()
        FROM memory_extraction_candidates candidate
        JOIN memory_claims claim ON claim.id = candidate.legacy_memory_claim_id
        WHERE claim.project_id IS NOT NULL
        ON CONFLICT (candidate_id, project_id, role) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO memory_candidate_project_bindings (
            id, candidate_id, project_id, role, status, method, confidence, rationale, created_at, updated_at
        )
        SELECT gen_random_uuid(), candidate.id, project.id, 'mentions', 'confirmed', 'migration', 1.0,
               'Source-bound legacy project relation.', now(), now()
        FROM memory_extraction_candidates candidate
        JOIN memory_claims claim ON claim.id = candidate.legacy_memory_claim_id
        JOIN memory_relations relation
          ON relation.memory_item_id = claim.memory_item_id
         AND relation.document_id = claim.document_id
         AND relation.relation_type = 'belongs_to_project'
         AND relation.target_type = 'project'
        JOIN projects project ON project.id::text = relation.target_id
        WHERE claim.project_id IS DISTINCT FROM project.id
        ON CONFLICT (candidate_id, project_id, role) DO NOTHING
    """))

    op.execute(sa.text("""
        INSERT INTO glossary_terms (id, canonical_term, normalized_term, aliases, entity_type, entity_id, created_at, updated_at)
        SELECT DISTINCT ON (regexp_replace(lower(btrim(entry.canonical_term)), '\\s+', ' ', 'g'))
               gen_random_uuid(), entry.canonical_term,
               regexp_replace(lower(btrim(entry.canonical_term)), '\\s+', ' ', 'g'),
               to_jsonb(COALESCE(entry.aliases, ARRAY[]::varchar[])), entry.entity_type, entry.entity_id,
               entry.created_at, entry.updated_at
        FROM glossary_entries entry
        ORDER BY regexp_replace(lower(btrim(entry.canonical_term)), '\\s+', ' ', 'g'), entry.created_at, entry.id
        ON CONFLICT (normalized_term) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO glossary_meanings (
            id, term_id, legacy_glossary_entry_id, definition, scope_candidate,
            resolution_status, resolution_method, resolution_rationale, confidence,
            visibility_tenant_id, created_at, updated_at
        )
        SELECT gen_random_uuid(), term.id, entry.id, COALESCE(NULLIF(entry.description, ''), entry.canonical_term),
               CASE WHEN entry.project_id IS NOT NULL THEN 'project'
                    WHEN entry.scope = 'global' THEN 'global'
                    ELSE 'unknown' END,
               CASE WHEN entry.project_id IS NOT NULL OR entry.scope = 'global'
                    THEN 'resolved' ELSE 'needs_review' END,
               'migration', 'Backfilled from the legacy glossary entry.',
               CASE WHEN entry.status = 'confirmed' THEN 1.0 ELSE 0.0 END,
               entry.tenant_id, entry.created_at, entry.updated_at
        FROM glossary_entries entry
        JOIN glossary_terms term
          ON term.normalized_term = regexp_replace(lower(btrim(entry.canonical_term)), '\\s+', ' ', 'g')
        ON CONFLICT (legacy_glossary_entry_id) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO glossary_meaning_project_bindings (
            id, meaning_id, project_id, status, method, confidence, rationale, created_at, updated_at
        )
        SELECT gen_random_uuid(), meaning.id, entry.project_id, 'confirmed', 'migration', 1.0,
               'Primary project from legacy glossary entry.', now(), now()
        FROM glossary_meanings meaning
        JOIN glossary_entries entry ON entry.id = meaning.legacy_glossary_entry_id
        WHERE entry.project_id IS NOT NULL
        ON CONFLICT (meaning_id, project_id) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO glossary_meaning_sources (
            id, meaning_id, legacy_glossary_observation_id, document_id,
            visibility_tenant_id, evidence_section_ids, created_at
        )
        SELECT gen_random_uuid(), meaning.id, observation.id, observation.document_id,
               observation.visibility_tenant_id,
               CASE WHEN observation.source_type = 'document' AND observation.source_ref LIKE '%:%:%'
                    THEN jsonb_build_array(split_part(observation.source_ref, ':', 3))
                    ELSE '[]'::jsonb END,
               observation.created_at
        FROM glossary_observations observation
        JOIN glossary_meanings meaning ON meaning.legacy_glossary_entry_id = observation.entry_id
        ON CONFLICT (meaning_id, legacy_glossary_observation_id) DO NOTHING
    """))


def downgrade() -> None:
    op.drop_index("ix_glossary_meaning_sources_document", table_name="glossary_meaning_sources")
    op.drop_table("glossary_meaning_sources")
    op.drop_index("ix_glossary_meaning_project_binding_project", table_name="glossary_meaning_project_bindings")
    op.drop_table("glossary_meaning_project_bindings")
    op.drop_index("ix_glossary_meanings_term_resolution", table_name="glossary_meanings")
    op.drop_table("glossary_meanings")
    op.drop_table("glossary_terms")
    op.drop_index("ix_memory_candidate_project_binding_project", table_name="memory_candidate_project_bindings")
    op.drop_table("memory_candidate_project_bindings")
    op.drop_index("ix_memory_candidates_subject", table_name="memory_extraction_candidates")
    op.drop_index("ix_memory_candidates_resolution", table_name="memory_extraction_candidates")
    op.drop_table("memory_extraction_candidates")
    op.drop_index("ix_document_memory_snapshots_document", table_name="document_memory_snapshots")
    op.drop_table("document_memory_snapshots")
