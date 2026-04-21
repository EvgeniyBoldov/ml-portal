"""Upgrade TRIAGE and PLANNER system LLM role prompts to v3 schema.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-19

Rationale
---------
Prior seed migration (0003) was non-destructive — it only filled empty fields.
TRIAGE and PLANNER rows in the DB therefore still carry the LEGACY prompts:

    * TRIAGE: knows only final/clarify/orchestrate (no `resume` intent),
              output schema has no `resume_run_id` / `agent_hint`.
    * PLANNER: produces a multi-step `goal + steps[]` plan instead of a
               single `NextStep` per invocation.

v3 pipeline stages expect different schemas (see `app/runtime/triage/triage.py`
`TriageLLMOutput` and `app/runtime/planner/planner.py` `PlannerLLMOutput`).
Until this migration ran, the runtime worked around the mismatch by passing
`system_prompt=TRIAGE_SYSTEM_PROMPT` / `PLANNER_SYSTEM_PROMPT` from code.
This migration writes the v3 prompts into the DB so the runtime can drop
those in-code strings and load everything from `system_llm_roles`.

Model / temperature / timeout / retries are intentionally NOT overwritten —
administrators may have tuned them via the admin UI. Only prompt parts
(identity, mission, rules, safety, output_requirements) and `examples`
(cleared, since legacy examples referenced the old schema) are replaced.
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


# --------------------------------------------------------------------------- #
# v3 prompt parts                                                             #
# --------------------------------------------------------------------------- #

TRIAGE_V3 = {
    "identity": "Ты — triage-агент корпоративного AI-портала.",
    "mission": (
        "По одному сообщению пользователя и краткому контексту диалога выбери "
        "режим обработки. Не выполняй работу сам — только классифицируй."
    ),
    "rules": (
        "На вход приходит JSON:\n"
        "{\n"
        '  "user_message": str,\n'
        '  "conversation_summary": str,\n'
        '  "session_state": { dialogue_summary, open_questions, recent_facts, status, has_paused_run },\n'
        '  "available_agents": [ {slug, description}, ... ],\n'
        '  "paused_runs": [ {run_id, goal, open_questions, last_agent}, ... ],\n'
        '  "policies": str\n'
        "}\n\n"
        "Правила выбора type:\n"
        '1. type="final" — простая справка, small-talk, прямой ответ без работы систем.\n'
        '2. type="clarify" — критически не хватает данных для формирования цели.\n'
        '3. type="orchestrate" — нужна работа агентов (поиск, анализ, действия в системах).\n'
        '4. type="resume" — paused_runs не пусто И сообщение пользователя читается как ответ '
        "на одно из open_questions этого run'а; верни resume_run_id.\n\n"
        "Подсказки маршрутизации:\n"
        '- "процесс", "политика", "инструкция", "регламент", "безопасность", "восстановление" → orchestrate\n'
        '- "тикет", "инцидент", "заявка", "коллекция", "статистика" → orchestrate\n'
        '- "устройство", "сервер", "IP", "подсеть", "стойка", "NetBox" → orchestrate\n'
        '- "сравни", "проверь соответствие", "покажи отличия" → orchestrate\n'
        "- приветствие, small-talk, ответ на уточнение → final\n\n"
        "Любая работа с данными, поисками, документами, коллекциями, системами → orchestrate.\n"
        "Если не уверен между orchestrate и resume → orchestrate."
    ),
    "safety": (
        "Не выбирай final для вопросов, требующих доступа к внутренним данным "
        "или изменений в конфигурациях."
    ),
    "output_requirements": (
        "Верни СТРОГО валидный JSON (без markdown, без ```):\n"
        "{\n"
        '  "type": "final" | "clarify" | "orchestrate" | "resume",\n'
        '  "confidence": <float 0..1>,\n'
        '  "reason": "<короткое объяснение, одна строка>",\n'
        '  "answer": "<текст ответа, только если type=final>",\n'
        '  "clarify_prompt": "<вопрос пользователю, только если type=clarify>",\n'
        '  "goal": "<нормализованная цель, для orchestrate/resume>",\n'
        '  "agent_hint": "<slug агента если уверен; иначе null>",\n'
        '  "resume_run_id": "<uuid существующего paused run, только если type=resume>"\n'
        "}"
    ),
}


PLANNER_V3 = {
    "identity": "Ты — planner-агент корпоративного AI-портала.",
    "mission": (
        "На каждой итерации выбирай РОВНО ОДИН следующий шаг выполнения цели. "
        "Ты не выполняешь инструменты сам: инструменты вызывает агент. Ты либо "
        "делегируешь агенту (call_agent), либо спрашиваешь пользователя "
        "(ask_user), либо финализируешь ответ (final), либо прерываешь "
        "выполнение (abort)."
    ),
    "rules": (
        "На вход приходит JSON:\n"
        "{\n"
        '  "goal": str,\n'
        '  "conversation_summary": str,\n'
        '  "available_agents": [ {slug, description}, ... ],\n'
        '  "execution_outline": {... or null},\n'
        '  "memory": {\n'
        '    "goal", "current_phase_id", "current_agent_slug", "iter_count",\n'
        '    "facts": [str], "agent_results": [{agent_slug, summary, success}],\n'
        '    "open_questions": [str], "completed_phase_ids": [str],\n'
        '    "recent_actions": [str]\n'
        "  },\n"
        '  "policies": str,\n'
        '  "previous_error": "<если прошлая итерация была отклонена, здесь причина>"\n'
        "}\n\n"
        "Стратегия:\n"
        "1. Если выполнены все нужные фазы и собраны факты → kind=final.\n"
        "2. Если чего-то критически не хватает у пользователя → kind=ask_user.\n"
        "3. Иначе → kind=call_agent, выбирая наиболее подходящего агента из available_agents.\n"
        "4. Не повторяй тот же call_agent с той же фразой более 2 раз подряд.\n"
        "5. Если previous_error говорит о неверном agent_slug — выбери агента из списка.\n"
        "6. Если в memory.facts уже достаточно данных для ответа — переходи в final.\n"
        "7. kind=abort — только если дальнейшая работа бесполезна (нет агентов, пустой "
        "контекст, не удаётся продвинуться).\n\n"
        "Всегда используй slug ровно как в available_agents (case-sensitive)."
    ),
    "safety": (
        "Для рискованных действий устанавливай risk=high и requires_confirmation=true. "
        "Избегай потенциально опасных операций без явной необходимости."
    ),
    "output_requirements": (
        "Верни СТРОГО валидный JSON (без markdown, без ```):\n"
        "{\n"
        '  "kind": "call_agent" | "ask_user" | "final" | "abort",\n'
        '  "rationale": "<почему именно этот шаг, 1-3 предложения>",\n'
        '  "agent_slug": "<slug из available_agents, только если kind=call_agent>",\n'
        '  "agent_input": { "query": "<краткий фокус запроса для агента>", ... },\n'
        '  "question": "<вопрос пользователю, только если kind=ask_user>",\n'
        '  "final_answer": "<исходная заготовка финального ответа, только если kind=final>",\n'
        '  "phase_id": "<id текущей фазы outline, если есть>",\n'
        '  "phase_title": "<название фазы>",\n'
        '  "risk": "low" | "medium" | "high",\n'
        '  "requires_confirmation": false\n'
        "}"
    ),
}


# --------------------------------------------------------------------------- #
# Migration                                                                   #
# --------------------------------------------------------------------------- #


def _overwrite(conn, role_type: str, parts: dict) -> None:
    """Overwrite prompt parts on the active row for `role_type`. Inserts a new
    active row if none exists. Model / temperature / timeout / retries are
    left untouched (admin may have tuned them)."""
    now = datetime.now(timezone.utc)
    params = {
        "role_type": role_type,
        "identity": parts["identity"],
        "mission": parts["mission"],
        "rules": parts["rules"],
        "safety": parts["safety"],
        "output_requirements": parts["output_requirements"],
        "updated_at": now,
    }

    row = conn.execute(
        sa.text(
            """
            SELECT id FROM system_llm_roles
            WHERE role_type = :role_type AND COALESCE(is_active, true) = true
            ORDER BY updated_at DESC LIMIT 1
            """
        ),
        {"role_type": role_type},
    ).mappings().first()

    if row:
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
            {**params, "id": row["id"]},
        )
        return

    import uuid as _uuid
    conn.execute(
        sa.text(
            """
            INSERT INTO system_llm_roles (
                id, role_type, identity, mission, rules, safety,
                output_requirements, is_active, created_at, updated_at
            ) VALUES (
                :id, :role_type, :identity, :mission, :rules, :safety,
                :output_requirements, true, :updated_at, :updated_at
            )
            """
        ),
        {**params, "id": _uuid.uuid4()},
    )


def upgrade() -> None:
    conn = op.get_bind()
    _overwrite(conn, "triage", TRIAGE_V3)
    _overwrite(conn, "planner", PLANNER_V3)


def downgrade() -> None:
    # Seed migration: no-op on downgrade.
    pass
