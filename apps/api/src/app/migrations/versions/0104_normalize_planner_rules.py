"""Normalize the active planner rules to the canonical vocabulary.

Revision ID: 0104
Revises: 0103
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0104"
down_revision = "0103"
branch_labels = None
depends_on = None


PLANNER_RULES = (
    "Используй только executor из available_agents. task_id уникален во всём run; "
    "depends_on ссылается только на задачи текущей iteration. Planner и synthesizer "
    "являются terminal invocations, а tasks всегда исполняются агентами. Каждую ранее "
    "незавершённую задачу закрой одной explicit resolution. Binding допустим только с "
    "continue_with_tasks, ведёт в одну из replacement_task_ids и связывает "
    "schema-compatible required output producer с consumer input. terminal=planner "
    "возвращает управление planner после завершения iteration. terminal=synthesis "
    "разрешён только при готовности к финальному ответу и требует synthesis_brief. Для "
    "каждого expected_output явно выбери fulfillment. fulfillment=artifact подтверждается "
    "только runtime-созданным файлом. fulfillment=verified_receipt требует непустой "
    "receipt_operations с допустимыми canonical operation names; receipt другой операции "
    "не засчитывается."
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE system_llm_roles
            SET rules = :rules
            WHERE role_type = 'planner' AND is_active = true
            """
        ),
        {"rules": PLANNER_RULES},
    )


def downgrade() -> None:
    raise RuntimeError("canonical planner vocabulary migration is irreversible")
