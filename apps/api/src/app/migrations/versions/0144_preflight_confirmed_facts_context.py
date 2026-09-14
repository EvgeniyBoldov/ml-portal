"""Expose confirmed facts to root routing and planner context.

Revision ID: 0144
Revises: 0143
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0144"
down_revision = "0143"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = :rules, updated_at = now()
        WHERE role_type = 'turn_preflight'
          AND COALESCE(is_active, true)
    """).bindparams(
        rules="Используй только user_request, mechanical_lookup, facts_context, continuation и recall_context из входного JSON. facts_context содержит confirmed user/tenant facts и runtime facts в исходной форме scope, subject, value, confidence. User/tenant facts — устойчивые defaults, runtime fact current_date задаёт сегодняшнюю дату и timezone; ни один из них не является текущим статусом внешней системы. Используй facts_context для разрешения «мой/наш», для подтверждённых project_hints и параметров работы; не выдумывай значение факта и не превращай его в текущий статус. Если факт однозначно задаёт проект, передай его ключ в task_brief.project_hints. При конфликте фактов или отсутствии ключа выбирай clarify, когда без него возникнет неверная область поиска. Глоссарий и долговременную document/project memory не считай загруженными: они доступны только через mechanical_lookup и route=recall. Не выдумывай проекты, сущности, идентификаторы, результаты инструментов или выполненные действия. Явная команда пользователя «запомни как факт» или «remember as a fact» для сообщённой им формулировки ВСЕГДА означает synthesis с memory_candidates: не выбирай для неё recall или planner, не создавай задачу store_memory и не требуй artifact. Выбирай recall только когда для ответа нужно долговременное корпоративное знание и recall_context ещё отсутствует; после recall_context route=recall запрещён. Выбирай planner, если нужны текущие данные внешней системы, инструмент, действие, проверка, поиск вне memory или многошаговая работа. Выбирай synthesis только когда ответ можно безопасно подготовить из входных данных без внешнего действия и новых данных. Для planner сохрани только подтверждённые project_hints, entity_hints, ограничения и ожидаемый результат; не создавай задачи, не выбирай агентов и не называй инструменты. Для recall не добавляй неизвестные project_keys или entity_ids. Для clarify задай один вопрос, устраняющий главную блокирующую неоднозначность. memory_candidates добавляй только для явно сформулированных пользователем устойчивых фактов или терминов; candidates не означают, что память сохранена.",
    ))


def downgrade() -> None:
    pass
