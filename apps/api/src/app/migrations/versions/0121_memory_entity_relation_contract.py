"""Persist typed entity-edge extraction for semantic memory.

Revision ID: 0121
Revises: 0120
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0121"
down_revision = "0120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET output_requirements = 'Верни JSON с items[]. item_type: term, description, relationship, rule, constraint или procedure. Каждый item содержит subject, content, scope, project_key, project_confidence, applicability, related_project_keys, related_entities (target_type, target_id, relation_type), evidence_section_ids, aliases и term_kind.',
            updated_at = now()
        WHERE role_type = 'document_memory_extractor'
    """))


def downgrade() -> None:
    pass
