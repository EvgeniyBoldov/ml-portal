"""Route explicit fact-memory requests away from the planner.

Revision ID: 0141
Revises: 0140
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0141"
down_revision = "0140"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = :rules, updated_at = now()
        WHERE role_type = 'turn_preflight'
          AND COALESCE(is_active, true)
    """).bindparams(
        rules="Используй только user_request, mechanical_lookup, continuation и recall_context из входного JSON. Не выдумывай факты, проекты, сущности, идентификаторы, результаты инструментов или выполненные действия. Явная команда пользователя «запомни как факт» или «remember as a fact» для сообщённой им формулировки ВСЕГДА означает synthesis с memory_candidates: не выбирай для неё recall или planner, не создавай задачу store_memory и не требуй artifact. Runtime сам передаст candidate в writeback памяти после ответа. Выбирай clarify, если ключевая цель, объект, проект или термин неоднозначны и без уточнения возможен неверный результат. Выбирай recall только когда для ответа нужно долговременное корпоративное знание и recall_context ещё отсутствует; после recall_context route=recall запрещён. Выбирай planner, если нужны текущие данные внешней системы, инструмент, действие, проверка, поиск вне memory или многошаговая работа. Выбирай synthesis только когда ответ можно безопасно подготовить из входных данных без внешнего действия и новых данных. При сомнении synthesis versus planner выбирай planner, если нужны актуальные данные; при сомнении recall versus planner выбирай recall только для долговременного знания, а не текущего состояния. Для synthesis answer_draft — внутренний материал Synthesizer, а не финальный ответ: он должен быть основан только на входе и явно отмечать неопределённость. Для planner сохрани только подтверждённые project_hints, entity_hints, ограничения и ожидаемый результат; не создавай задачи, не выбирай агентов и не называй инструменты. Для recall не добавляй неизвестные project_keys или entity_ids. Для clarify задай один вопрос, устраняющий главную блокирующую неоднозначность. memory_candidates добавляй только для явно сформулированных пользователем устойчивых фактов или терминов; candidates не означают, что память сохранена.",
    ))


def downgrade() -> None:
    pass
