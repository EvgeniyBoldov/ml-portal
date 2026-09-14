"""Refresh the extractor role contract for company and project memory.

Revision ID: 0115
Revises: 0114
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0115"
down_revision = "0114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules =
              'Каждый item обязан ссылаться на evidence_section_ids. Укажи scope=project только при ровно одном project_key из каталога и честном project_confidence; иначе для корпоративного правила или процедуры используй scope=company. Не превращай неясную проектную процедуру в общее правило. Процедуру возвращай единым content с целью, применимостью, шагами, проверкой и откатом, если они есть в документе.',
            output_requirements =
              'Верни JSON с items[]. item_type: term, description, relationship, rule, constraint или procedure. Каждый item содержит subject, content, scope, project_key, project_confidence, applicability, related_project_keys, evidence_section_ids, aliases и term_kind.',
            updated_at = now()
        WHERE role_type = 'document_memory_extractor'
          AND COALESCE(is_active, true)
          AND COALESCE(output_requirements, '') NOT ILIKE '%related_project_keys%'
    """))


def downgrade() -> None:
    pass
