"""Add FACT_EXTRACTOR and SUMMARY_COMPACTOR system LLM roles.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-19

Extends `system_llm_roles.role_type` CHECK constraint to accept
'fact_extractor' and 'summary_compactor', and seeds default active
rows for both. These roles drive the new memory helpers
(`FactExtractor`, `SummaryCompactor`) introduced as part of the
memory architecture refactor.

Rationale
---------
All runtime LLM calls must source their prompts from the DB — no
hardcoded strings in code. Adding new helpers requires adding new
roles, not introducing new constants.

Down-migration deletes the seeded rows first (otherwise tightening
the CHECK back would fail), then restores the previous constraint.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


FACT_EXTRACTOR_DEFAULTS = {
    "identity": "Ты — экстрактор фактов для корпоративного AI-портала.",
    "mission": (
        "Из одного хода диалога (сообщение пользователя + результаты агентов) "
        "извлеки компактные, атомарные факты, которые имеет смысл запомнить "
        "для будущих обращений этого пользователя или всего отдела."
    ),
    "rules": (
        "На вход приходит JSON: {user_message, agent_results, known_facts}.\n"
        "Верни СТРОГО JSON {\"facts\": [{scope, subject, value, confidence}]}.\n"
        "scope ∈ {user, chat, tenant}. subject — короткий ключ (snake/dot-case).\n"
        "Только стабильные факты: имя, роль, стек, стандарты. Максимум 8."
    ),
    "safety": (
        "Не извлекай секреты, пароли, токены, персональные данные сверх того "
        "что юзер сам указал в своём сообщении."
    ),
    "output_requirements": "Чистый JSON без пояснений и markdown.",
    "temperature": 0.1,
    "max_tokens": 800,
    "timeout_s": 15,
    "max_retries": 1,
    "retry_backoff": "none",
}


SUMMARY_COMPACTOR_DEFAULTS = {
    "identity": "Ты — компактор структурного саммари чата.",
    "mission": (
        "Обнови структурное саммари диалога на основе предыдущего состояния "
        "и дельты этого хода. Коротко и полезно для планера."
    ),
    "rules": (
        "На вход {previous, turn_delta, turn_number}.\n"
        "Верни {goals, done, entities, open_questions} — каждое поле\n"
        "JSON-массив/объект, элементы ≤ 120 символов, без дубликатов."
    ),
    "safety": "Не раскрывай секреты, токены, пароли.",
    "output_requirements": "Чистый JSON без пояснений и markdown.",
    "temperature": 0.2,
    "max_tokens": 800,
    "timeout_s": 20,
    "max_retries": 1,
    "retry_backoff": "none",
}


def _widen_constraint() -> None:
    op.drop_constraint(
        "check_system_llm_role_type", "system_llm_roles", type_="check"
    )
    op.create_check_constraint(
        "check_system_llm_role_type",
        "system_llm_roles",
        "role_type IN ('triage', 'planner', 'summary', 'memory', "
        "'synthesizer', 'fact_extractor', 'summary_compactor')",
    )


def _restore_prev_constraint() -> None:
    op.drop_constraint(
        "check_system_llm_role_type", "system_llm_roles", type_="check"
    )
    op.create_check_constraint(
        "check_system_llm_role_type",
        "system_llm_roles",
        "role_type IN ('triage', 'planner', 'summary', 'memory', 'synthesizer')",
    )


def _upsert_role(conn, role_type: str, defaults: dict) -> None:
    now = datetime.now(timezone.utc)
    existing = conn.execute(
        sa.text(
            "SELECT id FROM system_llm_roles "
            "WHERE role_type = :t AND COALESCE(is_active, true) = true "
            "ORDER BY updated_at DESC LIMIT 1"
        ),
        {"t": role_type},
    ).mappings().first()

    if existing:
        conn.execute(
            sa.text(
                """
                UPDATE system_llm_roles SET
                    identity = :identity, mission = :mission, rules = :rules,
                    safety = :safety, output_requirements = :output_requirements,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {**defaults, "id": existing["id"], "updated_at": now},
        )
        return

    conn.execute(
        sa.text(
            """
            INSERT INTO system_llm_roles (
                id, role_type, identity, mission, rules, safety,
                output_requirements, temperature, max_tokens, timeout_s,
                max_retries, retry_backoff, is_active, created_at, updated_at
            ) VALUES (
                :id, :role_type, :identity, :mission, :rules, :safety,
                :output_requirements, :temperature, :max_tokens, :timeout_s,
                :max_retries, :retry_backoff, true, :created_at, :updated_at
            )
            """
        ),
        {
            **defaults,
            "id": uuid.uuid4(),
            "role_type": role_type,
            "created_at": now,
            "updated_at": now,
        },
    )


def upgrade() -> None:
    _widen_constraint()
    conn = op.get_bind()
    _upsert_role(conn, "fact_extractor", FACT_EXTRACTOR_DEFAULTS)
    _upsert_role(conn, "summary_compactor", SUMMARY_COMPACTOR_DEFAULTS)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM system_llm_roles "
            "WHERE role_type IN ('fact_extractor', 'summary_compactor')"
        )
    )
    _restore_prev_constraint()
