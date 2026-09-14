"""Add evidence-only semantic-memory feedback.

Revision ID: 0112
Revises: 0111
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0112"
down_revision = "0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "memory_item_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("memory_item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tool_call_id", sa.String(length=128), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("evidence_refs", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("outcome IN ('confirmed', 'contradicted', 'insufficient', 'irrelevant')", name="ck_memory_item_evaluations_outcome"),
    )
    op.create_index("uq_memory_item_evaluations_item_call", "memory_item_evaluations", ["memory_item_id", "tool_call_id"], unique=True)
    op.create_index("ix_memory_item_evaluations_item_created", "memory_item_evaluations", ["memory_item_id", "created_at"])
    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint("check_system_llm_role_type", "system_llm_roles", "role_type IN ('planner', 'memory', 'synthesizer', 'fact_extractor', 'fact_compactor', 'document_memory_extractor', 'memory_evaluator')")
    op.execute(sa.text("""
        INSERT INTO system_llm_roles (id, role_type, identity, mission, rules, safety, output_requirements, model, temperature, max_tokens, timeout_s, max_retries, retry_backoff, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), 'memory_evaluator',
          'Ты — оценщик доверия к семантической памяти.',
          'Сравни MemoryItem только с переданным RAG evidence.',
          'Выбери confirmed, contradicted, insufficient или irrelevant. Не изменяй content и не используй agent answer как evidence.',
          'Не раскрывай секреты и не сохраняй raw payload.',
          'Верни строгий JSON с outcome, reason и evidence_hit_indexes.',
          'llm.llama4.scout', 0.0, 500, 30, 1, 'none', true, now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM system_llm_roles WHERE role_type = 'memory_evaluator' AND COALESCE(is_active, true))
    """))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM system_llm_roles WHERE role_type = 'memory_evaluator'"))
    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint("check_system_llm_role_type", "system_llm_roles", "role_type IN ('planner', 'memory', 'synthesizer', 'fact_extractor', 'fact_compactor', 'document_memory_extractor')")
    op.drop_table("memory_item_evaluations")
