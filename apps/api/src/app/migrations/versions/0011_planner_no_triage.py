"""Planner v3.1: absorb triage duties; retire TRIAGE role.

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-19

The Planner becomes the single decision engine in the runtime. Its
action vocabulary gains `direct_answer` and `clarify`, which subsume
the old `Triage` outcomes `FINAL_ANSWERED` / `CLARIFY_PAUSED`. The
dedicated TRIAGE LLM role is no longer invoked and is removed from
`system_llm_roles` to keep the admin UI honest.

Operations
----------
    * UPDATE the active PLANNER row with the new compiled prompt
      (v3_role_defaults.PLANNER_V3). The old prompt referred only to
      call_agent / ask_user / final / abort and must not leak into a
      running system once pipeline surgery lands.
    * DELETE all TRIAGE rows — nothing in the runtime touches this
      role anymore. Constraint NOT narrowed; `triage` stays in the
      CHECK allowlist as a dormant value so rollbacks and historic
      diagnostics don't fail.

Down-migration
--------------
Restores a best-effort copy of the pre-0011 PLANNER prompt (it is
inlined here to stay self-contained as required of Alembic scripts)
and re-seeds a minimal TRIAGE row so old code paths could hypothetically
be resurrected. This is strictly a safety net.
"""
from __future__ import annotations

from datetime import datetime, timezone
import uuid

from alembic import op
import sqlalchemy as sa


revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


PLANNER_V3_1 = {
    "model": "llm.llama.maverick",
    "identity": "Ты — planner-агент корпоративного AI-портала.",
    "mission": (
        "На каждой итерации выбирай РОВНО ОДИН следующий шаг выполнения цели. "
        "Ты — единственная точка принятия решений в рантайме. Триажа нет: "
        "любое сообщение пользователя приходит сразу к тебе, в том числе "
        "приветствия, small-talk, не-релевантные вопросы и уточнения."
    ),
    "rules": (
        "На вход приходит JSON: {goal, conversation_summary, available_agents, "
        "execution_outline, memory, policies, previous_error}.\n\n"
        "Выбор kind (ровно одно):\n"
        "* direct_answer — small-talk/общий вопрос без обращения к системам. "
        "Сразу пиши final_answer.\n"
        "* clarify — нужна одна уточняющая реплика пользователю. question обязателен.\n"
        "* call_agent — нужна реальная работа систем. Делегируй подходящему агенту "
        "из available_agents.\n"
        "* final — все нужные фазы выполнены и собраны факты.\n"
        "* abort — продвинуться нельзя.\n\n"
        "Правила:\n"
        "1. Нерелевантные/бытовые запросы → direct_answer, не зови агентов.\n"
        "2. Не повторяй call_agent с той же фразой более 2 раз подряд.\n"
        "3. agent_slug case-sensitive, строго из available_agents.\n"
        "4. Если memory.facts достаточно — kind=final.\n"
        "5. Перед call_agent убедись что задача в домене агентов (сеть, вирта, "
        "СХД, СРК, ДБА, скрипты, NetBox, коллекции, инциденты)."
    ),
    "safety": (
        "Для рискованных действий устанавливай risk=high и requires_confirmation=true."
    ),
    "output_requirements": (
        'Верни СТРОГО валидный JSON: {kind, rationale, agent_slug?, agent_input?, '
        'question?, final_answer?, phase_id?, phase_title?, risk, requires_confirmation}.'
    ),
    "temperature": 0.2,
    "max_tokens": 4096,
    "timeout_s": 60,
    "max_retries": 2,
    "retry_backoff": "linear",
}


# Minimal pre-0011 planner prompt (only used in downgrade for safety).
PLANNER_V3_0 = {
    **PLANNER_V3_1,
    "mission": (
        "Выбирай ровно один следующий шаг. Ты не выполняешь инструменты сам; "
        "делегируй агенту (call_agent), спрашивай пользователя (ask_user), "
        "финализируй ответ (final) или прерывай (abort)."
    ),
    "rules": (
        "Стратегия: все фазы + факты → final; критической информации нет → ask_user; "
        "иначе call_agent."
    ),
}


TRIAGE_V3_ROLLBACK_STUB = {
    "identity": "Ты — triage-агент (dormant, restored from rollback).",
    "mission": "Всегда отвечай type=orchestrate.",
    "rules": '{"type":"orchestrate"}',
    "safety": "",
    "output_requirements": '{"type":"orchestrate"}',
    "temperature": 0.1,
    "max_tokens": 200,
    "timeout_s": 10,
    "max_retries": 1,
    "retry_backoff": "none",
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
    _upsert_role(conn, "planner", PLANNER_V3_1)
    conn.execute(
        sa.text("DELETE FROM system_llm_roles WHERE role_type = 'triage'")
    )


def downgrade() -> None:
    conn = op.get_bind()
    _upsert_role(conn, "planner", PLANNER_V3_0)
    _upsert_role(conn, "triage", TRIAGE_V3_ROLLBACK_STUB)
