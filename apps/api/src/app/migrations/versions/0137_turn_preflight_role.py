"""Add the root TurnPreflight system role.

Revision ID: 0137
Revises: 0136
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0137"
down_revision = "0136"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint(
        "check_system_llm_role_type",
        "system_llm_roles",
        "role_type IN ('planner', 'memory', 'turn_preflight', 'synthesizer', 'fact_extractor', 'fact_compactor', 'document_memory_extractor', 'memory_evaluator')",
    )
    op.execute(sa.text("""
        INSERT INTO system_llm_roles (
            id, role_type, identity, mission, rules, safety, output_requirements,
            model, temperature, max_tokens, timeout_s, max_retries, retry_backoff,
            is_active, created_at, updated_at
        )
        SELECT gen_random_uuid(), 'turn_preflight',
            'Ты — TurnPreflight корпоративного AI-портала.',
            'Определи следующий runtime route для пользовательского turn и нормализуй вход следующей роли.',
            'Используй только user request, mechanical lookup, continuation и recall context. Не отвечай пользователю, не создавай план, не выбирай агента и не выполняй инструменты. Верни synthesis, planner, recall или clarify.',
            'Не раскрывай секреты и не считай candidates сохранёнными фактами.',
            'Верни строгий JSON TurnPreflightDecision.',
            'llm.llama4.scout', 0.1, 900, 20, 1, 'none', true, now(), now()
        WHERE NOT EXISTS (
            SELECT 1 FROM system_llm_roles
            WHERE role_type = 'turn_preflight' AND COALESCE(is_active, true)
        )
    """))


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM system_llm_roles WHERE role_type = 'turn_preflight'"))
    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint(
        "check_system_llm_role_type",
        "system_llm_roles",
        "role_type IN ('planner', 'memory', 'synthesizer', 'fact_extractor', 'fact_compactor', 'document_memory_extractor', 'memory_evaluator')",
    )
