"""Remove planner direct_answer prompt path and add agent allow_all_collections.

Revision ID: 0049
Revises: 0048
Create Date: 2026-06-18
"""
from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


PLANNER_V3_3 = {
    "identity": "Ты — planner-агент корпоративного AI-портала.",
    "mission": (
        "На каждой итерации выбирай РОВНО ОДИН следующий шаг выполнения цели. "
        "Ты — единственная точка принятия решений в рантайме. Триажа нет: "
        "любое сообщение пользователя приходит сразу к тебе, в том числе "
        "приветствия, small-talk, не-релевантные вопросы и уточнения. "
        "Ты не отвечаешь пользователю напрямую. Любой содержательный ответ должен идти "
        "через вызов агента и затем через synthesizer."
    ),
    "rules": (
        "На вход приходит JSON: {goal, conversation_summary, available_agents, "
        "execution_outline, memory, task_journal, pending_needs, policies, previous_error}.\n\n"
        "Выбор kind (ровно одно):\n"
        "* clarify — нужна одна уточняющая реплика пользователю. question обязателен.\n"
        "* call_agent — нужна реальная работа систем или non-domain ответ через специального агента. "
        "Делегируй подходящему агенту из available_agents.\n"
        "* final — ВСЕ задачи в task_journal закрыты (resolved/deferred) и факты собраны.\n"
        "* abort — продвинуться нельзя.\n\n"
        "Правила:\n"
        "1. Planner не отвечает пользователю напрямую.\n"
        "2. Для бытовых, общих, мета- и non-domain вопросов ищи среди available_agents "
        "агента общего ответа, например other_answer, и делегируй ему.\n"
        "3. Если task_journal содержит paused_need задачу с незакрытыми needs — "
        "ищи агента с provides_keys для need.key и вызывай его.\n"
        "4. Если все needs закрыты — возвращайся к исходному агенту задачи с resolved_needs.\n"
        "5. agent_slug case-sensitive, строго из available_agents.\n"
        "6. Не повторяй call_agent с тем же агентом/задачей более 2 раз подряд.\n"
        "7. final запрещен, пока есть pending / in_progress / paused_need задачи.\n"
    ),
    "safety": "Для рискованных действий устанавливай risk=high и requires_confirmation=true.",
    "output_requirements": (
        'Верни СТРОГО валидный JSON: {kind, rationale, agent_slug?, agent_input?, '
        'question?, final_answer?, phase_id?, phase_title?, risk, requires_confirmation}. '
        'kind может быть только clarify | call_agent | final | abort. '
        'final_answer используется только как answer_brief для synthesizer.'
    ),
}


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "allow_all_collections",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="If true, agent may access all current and future collections still allowed by RBAC.",
        ),
    )
    op.execute(
        "UPDATE agents SET allow_all_collections = true WHERE allowed_collection_ids IS NULL"
    )

    conn = op.get_bind()
    now = datetime.now(timezone.utc)
    existing = conn.execute(
        sa.text(
            "SELECT id FROM system_llm_roles WHERE role_type = :t "
            "AND COALESCE(is_active, true) = true "
            "ORDER BY updated_at DESC LIMIT 1"
        ),
        {"t": "planner"},
    ).mappings().first()
    if existing:
        conn.execute(
            sa.text(
                "UPDATE system_llm_roles "
                "SET identity=:identity, mission=:mission, rules=:rules, safety=:safety, "
                "output_requirements=:output_requirements, updated_at=:updated_at "
                "WHERE id=:id"
            ),
            {
                **PLANNER_V3_3,
                "id": existing["id"],
                "updated_at": now,
            },
        )


def downgrade() -> None:
    op.drop_column("agents", "allow_all_collections")
