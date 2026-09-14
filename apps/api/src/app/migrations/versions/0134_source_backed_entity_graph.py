"""Move entity aliases and project bindings behind source ACL.

Revision ID: 0134
Revises: 0133
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0134"
down_revision = "0133"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_entity_sources", sa.Column("canonical_name", sa.String(length=255), nullable=True))
    op.add_column("knowledge_entity_sources", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("knowledge_entity_sources", sa.Column("visibility_tenant_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("knowledge_entity_sources", sa.Column("evidence_section_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.create_foreign_key("fk_knowledge_entity_sources_project", "knowledge_entity_sources", "projects", ["project_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_knowledge_entity_sources_visibility_tenant", "knowledge_entity_sources", "tenants", ["visibility_tenant_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_knowledge_entity_sources_project", "knowledge_entity_sources", ["project_id"])
    op.execute(sa.text("""
        UPDATE knowledge_entity_sources source
        SET canonical_name = entity.canonical_name,
            project_id = entity.project_id,
            visibility_tenant_id = CASE WHEN document.scope = 'local' THEN document.tenant_id ELSE NULL END
        FROM knowledge_entities entity, ragdocuments document
        WHERE entity.id = source.entity_id AND document.id = source.document_id
    """))
    op.alter_column("knowledge_entity_sources", "canonical_name", nullable=False)
    op.drop_constraint("uq_knowledge_entity_sources_document", "knowledge_entity_sources", type_="unique")
    op.create_unique_constraint(
        "uq_knowledge_entity_sources_document", "knowledge_entity_sources",
        ["entity_id", "document_id", "canonical_checksum", "project_id"],
    )
    op.drop_index("ix_knowledge_entities_project", table_name="knowledge_entities")
    op.drop_column("knowledge_entities", "aliases")
    op.drop_column("knowledge_entities", "project_id")
    op.execute(sa.text("""
        UPDATE memory_claims SET state = 'stale', updated_at = now()
        WHERE item_type IN ('description', 'relationship') AND state <> 'stale'
    """))
    op.execute(sa.text("""
        UPDATE memory_items SET state = 'stale', updated_at = now()
        WHERE item_type IN ('description', 'relationship') AND state <> 'stale'
    """))
    op.execute(sa.text("""
        UPDATE glossary_observations
        SET state = 'stale'
        WHERE source_type = 'document' AND state <> 'stale'
    """))
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules =
            'Каждый item обязан ссылаться на evidence_section_ids. term.content: definition. description.content: summary, details. relationship.content: summary и хотя бы related_entities либо related_project_keys. Укажи scope=project только при ровно одном project_key из каталога и честном project_confidence; иначе используй scope=company. Не публикуй неполный нормативный item. procedure.content: goal, applicability_conditions, required_approvals, непустые prechecks, steps[] (instruction, expected_result, confirmation_required), непустая verification, rollback (mode=steps с steps[] либо mode=not_applicable с reason), exceptions. rule.content: statement, effect=require|forbid|allow, conditions, required_approvals, required_checks, exceptions, consequences. constraint.content: statement, conditions, непустой limits, exceptions, consequences. decision.content: decision, conditions, rationale, consequences.',
            updated_at = now()
        WHERE role_type = 'document_memory_extractor' AND COALESCE(is_active, true)
    """))


def downgrade() -> None:
    # Restoring ACL-blind aliases would be unsafe; this contract has no
    # downgrade path that reactivates semantic knowledge.
    pass
