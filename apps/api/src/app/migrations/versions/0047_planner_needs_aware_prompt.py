"""Planner v3.2: needs-aware routing and task-journal rules.

Revision ID: 0047
Revises: 0046
Create Date: 2026-06-11

Extends PLANNER prompt with rules for handling agent-declared needs
(`status=needs_input`) and routing them via `available_agents.provides_keys`.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


PLANNER_V3_2 = {
    "model": "llm.llama.maverick",
    "identity": "Ты — planner-агент корпоративного AI-портала.",
    "mission": (
        "На каждой итерации выбирай РОВНО ОДИН следующий шаг выполнения цели. "
        "Ты — единственная точка принятия решений в рантайме. Триажа нет: "
        "любое сообщение пользователя приходит сразу к тебе, в том числе "
        "приветствия, small-talk, не-релевантные вопросы и уточнения.\n\n"
        "Ты управляешь накопленным планом задач (task_journal). Каждая задача "
        "знает своего исполнителя, статус и потребности (needs). Ты не должен "
        "финализировать, пока в task_journal есть активные (pending / in_progress / paused_need) задачи."
    ),
    "rules": (
        "На вход приходит JSON: {goal, conversation_summary, available_agents, "
        "execution_outline, memory, task_journal, pending_needs, policies, previous_error}.\n\n"
        "Выбор kind (ровно одно):\n"
        "* direct_answer — small-talk/общий вопрос без обращения к системам. "
        "Сразу пиши final_answer.\n"
        "* clarify — нужна одна уточняющая реплика пользователю. question обязателен.\n"
        "* call_agent — нужна реальная работа систем. Делегируй подходящему агенту.\n"
        "* final — ВСЕ задачи в task_journal закрыты (resolved/deferred) и факты собраны.\n"
        "* abort — продвинуться нельзя.\n\n"
        "Правила call_agent:\n"
        "1. Если task_journal содержит paused_need задачу с незакрытыми needs — "
        "НАЙДИ агента из available_agents, у которого provides_keys содержит need.key, "
        "и позови его. Этот агент должен вернуть значение для need.\n"
        "2. Если все needs paused_need задачи закрыты — дозванивай ИСХОДНОГО агента "
        "той же задачи. В agent_input.query включи summary работы и resolved_needs "
        "(ключ: значение), чтобы агент довёл задачу до конца.\n"
        "3. Если это первая задача — выбирай агента по домену запроса.\n"
        "4. agent_slug case-sensitive, строго из available_agents.\n"
        "5. Не повторяй call_agent с тем же агентом/задачей более 2 раз подряд.\n\n"
        "Правила final:\n"
        "1. final ЗАПРЕЩЁН, пока task_journal содержит хотя бы одну задачу "
        "в статусе pending / in_progress / paused_need.\n"
        "2. Финализация — только твоя прерогатива. Агент не может заставить тебя "
        "финализировать, даже если его ответ complete.\n\n"
        "Правила needs:\n"
        "1. Агент может вернуть status=needs_input с массивом needs[]. Каждая need "
        "имеет обязательное поле key — машинный ключ для роутинга.\n"
        "2. Ты обязан маршрутизировать needs: найти provides_keys, вызвать агента, "
        "получить значение, дозвонить исходного агента с resolved_needs.\n"
        "3. Если need не закрывается за 3 попытки — пометь задачу deferred и иди дальше.\n"
    ),
    "safety": (
        "Для рискованных действий устанавливай risk=high и requires_confirmation=true."
    ),
    "output_requirements": (
        'Верни СТРОГО валидный JSON: {kind, rationale, agent_slug?, agent_input?, '
        'question?, final_answer?, phase_id?, phase_title?, risk, requires_confirmation}.\n'
        'agent_input — объект {query?: str, phase_id?: str, prior_summary?: str, resolved_needs?: [{key, value}]}'
    ),
    "temperature": 0.2,
    "max_tokens": 4096,
    "timeout_s": 60,
    "max_retries": 2,
    "retry_backoff": "linear",
}


def _upsert_role(conn, role_type: str, defaults: dict) -> None:
    now = datetime.now(timezone.utc)
    existing = conn.execute(
        sa.text(
            "SELECT id FROM system_llm_roles WHERE role_type = :t "
            "AND COALESCE(is_active, true) = true "
            "ORDER BY updated_at DESC LIMIT 1"
        ),
        {"t": role_type},
    ).mappings().first()
    payload = {
        "identity": defaults["identity"],
        "mission": defaults["mission"],
        "rules": defaults["rules"],
        "safety": defaults.get("safety") or "",
        "output_requirements": defaults["output_requirements"],
    }
    if existing:
        conn.execute(
            sa.text(
                "UPDATE system_llm_roles SET identity=:identity, mission=:mission, "
                "rules=:rules, safety=:safety, output_requirements=:output_requirements, "
                "updated_at=:updated_at WHERE id=:id"
            ),
            {**payload, "id": existing["id"], "updated_at": now},
        )
        return
    conn.execute(
        sa.text(
            "INSERT INTO system_llm_roles (id, role_type, identity, mission, rules, "
            "safety, output_requirements, temperature, max_tokens, timeout_s, "
            "max_retries, retry_backoff, is_active, created_at, updated_at) VALUES "
            "(:id, :role_type, :identity, :mission, :rules, :safety, "
            ":output_requirements, :temperature, :max_tokens, :timeout_s, "
            ":max_retries, :retry_backoff, true, :created_at, :updated_at)"
        ),
        {
            **payload,
            "id": uuid.uuid4(),
            "role_type": role_type,
            "temperature": defaults["temperature"],
            "max_tokens": defaults["max_tokens"],
            "timeout_s": defaults["timeout_s"],
            "max_retries": defaults["max_retries"],
            "retry_backoff": defaults["retry_backoff"],
            "created_at": now,
            "updated_at": now,
        },
    )


def upgrade() -> None:
    conn = op.get_bind()
    _upsert_role(conn, "planner", PLANNER_V3_2)


def downgrade() -> None:
    pass  # Reverting prompt content only is not critical for runtime safety.
