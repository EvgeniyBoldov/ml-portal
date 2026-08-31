"""Describe planner checkpoints in the untouched planner default.

Revision ID: 0093
Revises: 0092
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None


_PREVIOUS_RULES = (
    "Верни только смысловую мутацию графа. Runtime сам определяет initial/replan, "
    "ревизию, trigger и lifecycle. Для работы с графом используй action=apply_graph; "
    "для запроса данных — ask_user; при достижении цели — complete; при невозможности "
    "продолжить — fail. Используй executor только из available_agents. Не создавай циклы. "
    "Никогда не создавай поле needs: needs объявляет только исполнитель после реальной "
    "попытки выполнения. Для каждого pending need добавь задачу-производитель с "
    "expected_outputs, содержащим тот же key, и свяжи её с ожидающей задачей через "
    "depends_on; либо используй ask_user с одним конкретным вопросом; либо fail."
)
_NEW_RULES = (
    _PREVIOUS_RULES
    + " Для обычной работы создавай kind=agent и executor из available_agents. "
    "Когда дальнейшие шаги зависят от результатов нескольких задач, добавь kind=planner "
    "без executor: его depends_on образуют checkpoint, после которого planner получит "
    "сохранённый граф и продолжит планирование."
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE system_llm_roles SET rules = :new_rules "
            "WHERE role_type = 'planner' AND is_active = true AND rules = :previous_rules"
        ),
        {"previous_rules": _PREVIOUS_RULES, "new_rules": _NEW_RULES},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE system_llm_roles SET rules = :previous_rules "
            "WHERE role_type = 'planner' AND is_active = true AND rules = :new_rules"
        ),
        {"previous_rules": _PREVIOUS_RULES, "new_rules": _NEW_RULES},
    )
