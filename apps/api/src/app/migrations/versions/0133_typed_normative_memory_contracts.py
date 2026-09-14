"""Require strict content contracts for normative semantic memory.

Revision ID: 0133
Revises: 0132
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0133"
down_revision = "0132"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing arbitrary JSON cannot be safely adapted into a procedure or a
    # policy contract. Preserve provenance but withdraw it until the current
    # source is re-extracted by the controlled maintenance batch.
    op.execute(sa.text("""
        UPDATE memory_claims
        SET state = 'stale', updated_at = now()
        WHERE item_type IN ('rule', 'constraint', 'procedure', 'decision')
          AND state <> 'stale'
    """))
    op.execute(sa.text("""
        UPDATE memory_items
        SET state = 'stale', updated_at = now()
        WHERE item_type IN ('rule', 'constraint', 'procedure', 'decision')
          AND state <> 'stale'
    """))
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules =
            'Каждый item обязан ссылаться на evidence_section_ids. Укажи scope=project только при ровно одном project_key из каталога и честном project_confidence; иначе для корпоративного правила или процедуры используй scope=company. Не публикуй неполный нормативный item. procedure.content: goal, applicability_conditions, required_approvals, непустые prechecks, steps[] (instruction, expected_result, confirmation_required), непустая verification, rollback (mode=steps с steps[] либо mode=not_applicable с reason), exceptions. rule.content: statement, effect=require|forbid|allow, conditions, required_approvals, required_checks, exceptions, consequences. constraint.content: statement, conditions, непустой limits, exceptions, consequences. decision.content: decision, conditions, rationale, consequences.',
            output_requirements =
            'Верни JSON с items[]. item_type: term, description, relationship, rule, constraint, procedure или decision. Каждый item содержит subject, content, scope, project_key, project_confidence, applicability, related_project_keys, related_entities (target_type, target_id, relation_type), evidence_section_ids, aliases и term_kind. Для rule, constraint, procedure и decision content обязан соответствовать строгому контракту из rules.',
            updated_at = now()
        WHERE role_type = 'document_memory_extractor'
          AND COALESCE(is_active, true)
    """))


def downgrade() -> None:
    # State is intentionally not reactivated: old JSON has no safe contract.
    pass
