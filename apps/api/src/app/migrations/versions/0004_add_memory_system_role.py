"""Add memory role type and seed defaults for summary/memory

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-13
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


SUMMARY_DEFAULTS = {
    "identity": "Ты summary-агент корпоративного AI-портала.",
    "mission": "Собирай краткое и точное резюме диалога и результата выполнения за текущий цикл.",
    "rules": "Выделяй главное: цель, сделанные шаги, полученные факты, ограничения и открытые вопросы. Не добавляй неподтвержденных выводов.",
    "safety": "Не включай чувствительные данные, токены, пароли, ключи и внутренние секреты.",
    "output_requirements": "Верни связный краткий текст на русском языке без markdown-разметки.",
    "temperature": 0.1,
    "max_tokens": 1500,
    "timeout_s": 10,
    "max_retries": 2,
    "retry_backoff": "linear",
}

MEMORY_DEFAULTS = {
    "identity": "Ты memory-агент корпоративного AI-портала.",
    "mission": "Формируй и поддерживай рабочую память выполнения: факты, допущения, риски и незакрытые вопросы.",
    "rules": "Сохраняй только проверяемые факты и полезный контекст для следующих шагов. Убирай шум, не дублируй уже известное, отмечай неопределенности явно.",
    "safety": "Не сохраняй секреты, персональные данные и чувствительные артефакты в явном виде.",
    "output_requirements": "Верни JSON-объект с ключами facts, open_questions, risks, next_actions. Каждое значение — массив коротких строк на русском.",
    "temperature": 0.1,
    "max_tokens": 1200,
    "timeout_s": 10,
    "max_retries": 2,
    "retry_backoff": "linear",
}


def _upsert_role(conn, role_type: str, defaults: dict) -> None:
    now = datetime.now(timezone.utc)
    row = conn.execute(
        sa.text(
            """
            SELECT id
            FROM system_llm_roles
            WHERE role_type = :role_type AND COALESCE(is_active, true) = true
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ),
        {"role_type": role_type},
    ).mappings().first()

    params = {
        "identity": defaults.get("identity"),
        "mission": defaults.get("mission"),
        "rules": defaults.get("rules"),
        "safety": defaults.get("safety"),
        "output_requirements": defaults.get("output_requirements"),
        "model": defaults.get("model"),
        "temperature": defaults.get("temperature"),
        "max_tokens": defaults.get("max_tokens"),
        "timeout_s": defaults.get("timeout_s"),
        "max_retries": defaults.get("max_retries"),
        "retry_backoff": defaults.get("retry_backoff"),
        "updated_at": now,
    }

    if row:
        conn.execute(
            sa.text(
                """
                UPDATE system_llm_roles
                SET
                    identity = CASE WHEN identity IS NULL OR btrim(identity) = '' THEN :identity ELSE identity END,
                    mission = CASE WHEN mission IS NULL OR btrim(mission) = '' THEN :mission ELSE mission END,
                    rules = CASE WHEN rules IS NULL OR btrim(rules) = '' THEN :rules ELSE rules END,
                    safety = CASE WHEN safety IS NULL OR btrim(safety) = '' THEN :safety ELSE safety END,
                    output_requirements = CASE WHEN output_requirements IS NULL OR btrim(output_requirements) = '' THEN :output_requirements ELSE output_requirements END,
                    model = CASE WHEN model IS NULL OR btrim(model) = '' THEN :model ELSE model END,
                    temperature = COALESCE(temperature, :temperature),
                    max_tokens = COALESCE(max_tokens, :max_tokens),
                    timeout_s = COALESCE(timeout_s, :timeout_s),
                    max_retries = COALESCE(max_retries, :max_retries),
                    retry_backoff = COALESCE(retry_backoff, :retry_backoff),
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {**params, "id": row["id"]},
        )
        return

    conn.execute(
        sa.text(
            """
            INSERT INTO system_llm_roles (
                id, role_type, identity, mission, rules, safety, output_requirements,
                model, temperature, max_tokens, timeout_s, max_retries, retry_backoff,
                is_active, created_at, updated_at
            ) VALUES (
                :id, :role_type, :identity, :mission, :rules, :safety, :output_requirements,
                :model, :temperature, :max_tokens, :timeout_s, :max_retries, :retry_backoff,
                true, :created_at, :updated_at
            )
            """
        ),
        {
            **params,
            "id": uuid.uuid4(),
            "role_type": role_type,
            "created_at": now,
        },
    )


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            DO $$
            DECLARE role_type_ck text;
            BEGIN
              SELECT conname INTO role_type_ck
              FROM pg_constraint
              WHERE conrelid = 'system_llm_roles'::regclass
                AND contype = 'c'
                AND pg_get_constraintdef(oid) ILIKE '%role_type%'
              LIMIT 1;

              IF role_type_ck IS NOT NULL THEN
                EXECUTE format('ALTER TABLE system_llm_roles DROP CONSTRAINT %I', role_type_ck);
              END IF;
            END $$;
            """
        )
    )

    conn.execute(
        sa.text(
            """
            ALTER TABLE system_llm_roles
            ADD CONSTRAINT check_system_llm_role_type
            CHECK (role_type IN ('triage', 'planner', 'summary', 'memory'))
            """
        )
    )

    _upsert_role(conn, "summary", SUMMARY_DEFAULTS)
    _upsert_role(conn, "memory", MEMORY_DEFAULTS)


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM system_llm_roles WHERE role_type = 'memory'"))

    conn.execute(sa.text("ALTER TABLE system_llm_roles DROP CONSTRAINT IF EXISTS check_system_llm_role_type"))
    conn.execute(
        sa.text(
            """
            ALTER TABLE system_llm_roles
            ADD CONSTRAINT check_system_llm_role_type
            CHECK (role_type IN ('triage', 'planner', 'summary'))
            """
        )
    )
