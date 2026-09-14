"""Add document-derived semantic memory and its extractor role.

Revision ID: 0111
Revises: 0110
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("system_llm_roles", "role_type", type_=sa.String(length=32), existing_type=sa.String(length=20))
    op.create_table(
        "memory_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("normalized_subject", sa.String(length=200), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("scope IN ('company', 'project')", name="ck_memory_items_scope"),
        sa.CheckConstraint("state IN ('active', 'stale', 'uncertain')", name="ck_memory_items_state"),
        sa.CheckConstraint("item_type IN ('description', 'relationship', 'rule', 'constraint', 'procedure')", name="ck_memory_items_type"),
    )
    op.create_index("ix_memory_items_project_active", "memory_items", ["project_id", "state"])
    op.create_index("ix_memory_items_scope_subject", "memory_items", ["scope", "subject"])
    op.create_table(
        "memory_item_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("memory_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ragdocuments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_checksum", sa.String(length=128), nullable=False),
        sa.Column("section_id", sa.String(length=128), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("excerpt_hash", sa.String(length=128), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("uq_memory_item_sources_binding", "memory_item_sources", ["memory_item_id", "document_id", "canonical_checksum", "section_id"], unique=True)
    op.create_index("ix_memory_item_sources_document", "memory_item_sources", ["document_id", "canonical_checksum"])
    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint("check_system_llm_role_type", "system_llm_roles", "role_type IN ('planner', 'memory', 'synthesizer', 'fact_extractor', 'fact_compactor', 'document_memory_extractor')")
    op.execute(sa.text("""
        INSERT INTO system_llm_roles (id, role_type, identity, mission, rules, safety, output_requirements, model, temperature, max_tokens, timeout_s, max_retries, retry_backoff, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), 'document_memory_extractor',
          'Ты — экстрактор семантической памяти из корпоративных документов.',
          'Извлекай подтверждённые термины, правила, ограничения, описания и процедуры.',
          'Каждый item обязан ссылаться на section evidence. Project item требует одного project_key и confidence; при неясности возвращай только term.',
          'Не извлекай секреты, credentials и неподтверждённые сведения.',
          'Верни строгий JSON с items[].',
          'llm.llama4.scout', 0.0, 2400, 60, 1, 'none', true, now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM system_llm_roles WHERE role_type = 'document_memory_extractor' AND COALESCE(is_active, true))
    """))


def downgrade() -> None:
    # Remove the new value before restoring the legacy check constraint.
    op.execute(sa.text("DELETE FROM system_llm_roles WHERE role_type = 'document_memory_extractor'"))
    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint("check_system_llm_role_type", "system_llm_roles", "role_type IN ('planner', 'memory', 'synthesizer', 'fact_extractor', 'fact_compactor')")
    op.alter_column("system_llm_roles", "role_type", type_=sa.String(length=20), existing_type=sa.String(length=32))
    op.drop_table("memory_item_sources")
    op.drop_table("memory_items")
