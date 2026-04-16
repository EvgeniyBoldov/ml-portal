"""Seed default Russian configs for triage/planner system llm roles

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-13
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


TRIAGE_DEFAULTS = {
    "identity": "Ты триаж-агент корпоративного AI-портала. Твоя задача — выбрать правильный маршрут обработки запроса.",
    "mission": (
        "Проанализируй запрос пользователя и контекст диалога, затем выбери одно из действий: "
        "final (ответить сразу), clarify (уточнить недостающие данные) "
        "или orchestrate (передать задачу в оркестрацию агентам)."
    ),
    "rules": (
        "Правила:\n"
        "1. type=\"final\": простой вопрос, справка, small-talk — ответь в поле \"answer\".\n"
        "2. type=\"clarify\": не хватает ключевых данных — задай вопрос в \"clarify_prompt\".\n"
        "3. type=\"orchestrate\": нужен поиск в системах, анализ данных, сравнение или многошаговая работа — сформируй \"goal\" и при необходимости \"inputs\".\n\n"
        "Критичные подсказки маршрутизации:\n"
        "- процесс, политика, инструкция, регламент, безопасность, восстановление → orchestrate\n"
        "- тикет, инцидент, заявка, коллекция, статистика → orchestrate\n"
        "- устройство, сервер, IP, подсеть, стойка, NetBox → orchestrate\n"
        "- сравни, проверь соответствие, покажи отличия → orchestrate\n"
        "- приветствие, small-talk, ответ на уточнение → final\n\n"
        "Никогда не используй значения type, отличные от final, clarify, orchestrate."
    ),
    "safety": "Не выбирай final для запросов, связанных с внутренними системами, изменениями конфигураций или операционными рисками.",
    "output_requirements": (
        "Верни ТОЛЬКО валидный JSON (без markdown и без ```).\\n"
        "{\\n"
        "  \"type\": \"final\" | \"clarify\" | \"orchestrate\",\\n"
        "  \"confidence\": 0.0-1.0,\\n"
        "  \"reason\": \"краткое объяснение выбора\",\\n"
        "  \"answer\": \"текст ответа (только если type=final)\",\\n"
        "  \"clarify_prompt\": \"вопрос пользователю (только если type=clarify)\",\\n"
        "  \"goal\": \"цель оркестрации (только если type=orchestrate)\",\\n"
        "  \"inputs\": {}\\n"
        "}"
    ),
    "temperature": 0.3,
    "max_tokens": 1000,
    "timeout_s": 10,
    "max_retries": 2,
    "retry_backoff": "linear",
}

PLANNER_DEFAULTS = {
    "identity": "Ты planner-агент корпоративного AI-портала. Ты строишь короткий и выполнимый следующий шаг.",
    "mission": (
        "Разбивай цель на последовательные действия. "
        "Каждый рабочий шаг делегируй доступному агенту (kind=\"agent\"). "
        "Не вызывай инструменты напрямую: инструменты вызывает агент. "
        "kind=\"llm\" используй в основном для финального синтеза ответа."
    ),
    "rules": (
        "Правила:\n"
        "1. Начинай с делегирования агенту (kind=\"agent\"), если есть подходящий агент.\n"
        "2. Если дан execution_outline, иди по фазам по порядку; не пропускай must_do=true.\n"
        "3. Учитывай previous_observations в session_state; не повторяй уже выполненный полезный шаг.\n"
        "4. Когда обязательные фазы закрыты или фактов достаточно, переходи к kind=\"llm\" для финального ответа.\n"
        "5. kind=\"ask_user\" — только в крайнем случае, когда без уточнения нельзя двигаться дальше.\n"
        "6. План должен быть минимальным: один следующий шаг на итерацию.\n"
        "7. Верни только валидный JSON без markdown и без ```."
    ),
    "safety": "Для рискованных действий требуй подтверждение и избегай потенциально опасных операций без явной необходимости.",
    "output_requirements": (
        "Верни только валидный JSON с полями goal и steps. "
        "Формат шага: {\"step_id\":\"s1\",\"title\":\"...\",\"kind\":\"agent\"|\"ask_user\"|\"llm\","
        "\"ref\":\"<agent_slug>\",\"input\":{\"query\":\"...\",\"phase_id\":\"...\",\"phase_title\":\"...\"}}."
    ),
    "model": "llm.llama.maverick",
    "temperature": 0.2,
    "max_tokens": 4096,
    "timeout_s": 60,
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

    if row:
        role_id = row["id"]
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
            {
                "id": role_id,
                "updated_at": now,
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
            },
        )
        return

    conn.execute(
        sa.text(
            """
            INSERT INTO system_llm_roles (
                id,
                role_type,
                identity,
                mission,
                rules,
                safety,
                output_requirements,
                model,
                temperature,
                max_tokens,
                timeout_s,
                max_retries,
                retry_backoff,
                is_active,
                created_at,
                updated_at
            ) VALUES (
                :id,
                :role_type,
                :identity,
                :mission,
                :rules,
                :safety,
                :output_requirements,
                :model,
                :temperature,
                :max_tokens,
                :timeout_s,
                :max_retries,
                :retry_backoff,
                true,
                :created_at,
                :updated_at
            )
            """
        ),
        {
            "id": uuid.uuid4(),
            "role_type": role_type,
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
            "created_at": now,
            "updated_at": now,
        },
    )


def upgrade() -> None:
    conn = op.get_bind()
    _upsert_role(conn, "triage", TRIAGE_DEFAULTS)
    _upsert_role(conn, "planner", PLANNER_DEFAULTS)


def downgrade() -> None:
    # Seed migration: data rollback is intentionally no-op.
    pass
