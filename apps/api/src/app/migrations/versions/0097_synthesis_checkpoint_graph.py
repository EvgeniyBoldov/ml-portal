"""Make synthesis a terminal persisted graph checkpoint.

Revision ID: 0097
Revises: 0096
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0097"
down_revision = "0096"
branch_labels = None
depends_on = None


_PLANNER_RULES = (
    "Верни только смысловую мутацию графа. Runtime сам определяет initial/replan, "
    "ревизию, trigger и lifecycle. Для работы с графом используй action=apply_graph; "
    "для запроса данных — ask_user; при невозможности продолжить — fail. Используй "
    "executor только из available_agents. Каждый normal plan обязан содержать ровно "
    "один terminal kind=synthesis без executor, inputs, outputs, needs и depends_on. "
    "Его intent/instructions задают перефразированный вопрос пользователя, цель, "
    "направление и требования к финальному ответу. Planner checkpoints разрешены "
    "только до synthesis. Не создавай циклы и не объявляй needs: needs объявляет "
    "только исполнитель после реальной попытки выполнения. Для pending need добавь "
    "задачу-производитель с expected_outputs и свяжи её с ожидающей задачей через "
    "depends_on; либо ask_user с одним конкретным вопросом; либо fail."
)
_PLANNER_OUTPUT = (
    "Строгий JSON: action, tasks, remove_task_ids, question, failure_reason. "
    "action: apply_graph | ask_user | fail. tasks содержат task_id, kind, executor, "
    "intent, instructions, inputs, expected_outputs, depends_on, on_success и freshness_policy."
)
_SYNTH_MISSION = "Сформируй точный и удобный для пользователя ответ по synthesis task и completed task reports."
_SYNTH_RULES = (
    "Сохраняй направление synthesis task и опирайся только на completed task reports "
    "и их verified sources. Не добавляй новых фактов, внутренних деталей и ссылок."
)


def upgrade() -> None:
    op.drop_column("runtime_plans", "answer_brief")
    op.drop_column("platform_settings", "synth_chunk_size")
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE system_llm_roles SET rules = :rules, output_requirements = :output "
            "WHERE role_type = 'planner' AND is_active = true"
        ),
        {"rules": _PLANNER_RULES, "output": _PLANNER_OUTPUT},
    )
    bind.execute(
        sa.text(
            "UPDATE system_llm_roles SET mission = :mission, rules = :rules "
            "WHERE role_type = 'synthesizer' AND is_active = true"
        ),
        {"mission": _SYNTH_MISSION, "rules": _SYNTH_RULES},
    )


def downgrade() -> None:
    # The removed answer_brief and post-plan finalization contract are not restored.
    pass
