"""Add SYNTHESIZER system LLM role.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-19

Adds 'synthesizer' to the `role_type` CHECK constraint on
`system_llm_roles` and seeds a default active row. This lets
`app.runtime.synthesizer.Synthesizer` load its system prompt and
execution knobs from the DB instead of carrying hardcoded strings.

Rationale:
    Prior to this migration the synthesizer was the last runtime
    component with an in-code prompt (`DEFAULT_SYSTEM_PROMPT`). That
    prompt was invisible to admins and could not be A/B-tested. Moving
    it under `system_llm_roles` gives ops a single pane of glass for all
    runtime LLM roles (triage / planner / summary / memory / synthesizer).

Schema change:
    The role_type CHECK constraint previously only allowed the four
    original roles. It is dropped and recreated to include 'synthesizer'.
    Down-migration restores the old constraint AFTER deleting any
    synthesizer rows (otherwise the CHECK would fail).
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


SYNTHESIZER_DEFAULTS = {
    "identity": "Ты — старший инженер корпоративного AI-портала.",
    "mission": (
        "Сформируй точный, лаконичный и структурированный ответ для пользователя "
        "на основе предоставленных фактов и промежуточных результатов агентов."
    ),
    "rules": (
        "Не придумывай того, чего нет в фактах. "
        "Если данных не хватает — честно отметь это в конце ответа. "
        "Отвечай на русском, если пользователь писал на русском; иначе — на языке пользователя. "
        "Не добавляй служебных оговорок про инструменты, планировщика и внутреннюю кухню."
    ),
    "safety": "Не раскрывай секреты, токены, пароли и внутренние идентификаторы в финальном тексте.",
    "output_requirements": (
        "Формат ответа — связный читаемый текст (markdown допускается только для "
        "структурирования списков/таблиц/кода, если это помогает восприятию)."
    ),
    "temperature": 0.3,
    "max_tokens": 2000,
    "timeout_s": 60,
    "max_retries": 1,
    "retry_backoff": "none",
}


def upgrade() -> None:
    # 1. Widen the CHECK constraint to accept 'synthesizer'.
    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint(
        "check_system_llm_role_type",
        "system_llm_roles",
        "role_type IN ('triage', 'planner', 'summary', 'memory', 'synthesizer')",
    )

    # 2. Upsert the default active synthesizer row.
    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    row = conn.execute(
        sa.text(
            """
            SELECT id FROM system_llm_roles
            WHERE role_type = 'synthesizer' AND COALESCE(is_active, true) = true
            ORDER BY updated_at DESC LIMIT 1
            """
        )
    ).mappings().first()

    if row:
        # Existing row (shouldn't happen on a clean DB, but idempotent update):
        conn.execute(
            sa.text(
                """
                UPDATE system_llm_roles SET
                    identity = :identity,
                    mission = :mission,
                    rules = :rules,
                    safety = :safety,
                    output_requirements = :output_requirements,
                    examples = NULL,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {**SYNTHESIZER_DEFAULTS, "id": row["id"], "updated_at": now},
        )
    else:
        conn.execute(
            sa.text(
                """
                INSERT INTO system_llm_roles (
                    id, role_type, identity, mission, rules, safety,
                    output_requirements, temperature, max_tokens, timeout_s,
                    max_retries, retry_backoff, is_active, created_at, updated_at
                ) VALUES (
                    :id, 'synthesizer', :identity, :mission, :rules, :safety,
                    :output_requirements, :temperature, :max_tokens, :timeout_s,
                    :max_retries, :retry_backoff, true, :created_at, :updated_at
                )
                """
            ),
            {
                **SYNTHESIZER_DEFAULTS,
                "id": uuid.uuid4(),
                "created_at": now,
                "updated_at": now,
            },
        )


def downgrade() -> None:
    # Clear synthesizer rows first; otherwise the tightened CHECK would fail.
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM system_llm_roles WHERE role_type = 'synthesizer'"))

    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint(
        "check_system_llm_role_type",
        "system_llm_roles",
        "role_type IN ('triage', 'planner', 'summary', 'memory')",
    )
