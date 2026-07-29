"""Make the initial planner revision contract unambiguous.

Only the untouched standard planner prompt is updated. Operator-edited
planner prompts remain authoritative and are not overwritten.
"""

import sqlalchemy as sa
from alembic import op


revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


_CURRENT_RULES = (
    "Верни мутацию графа. Используй только available_agents; "
    "expected_revision — текущая plan.revision ДО применения мутации, "
    "а не будущая ревизия. Для первого create_plan при plan.revision=0 "
    "всегда верни expected_revision=0. Не создавай циклы. "
    "Решения: create_plan, revise_plan, ask_user, complete_plan, fail_plan."
)

_STRENGTHENED_RULES = (
    "Верни мутацию графа. Используй только available_agents и строго соблюдай "
    "текущую ревизию плана ДО применения мутации. "
    "Если plan.revision=0 и план ещё не содержит tasks, единственно допустимая "
    "начальная мутация — decision=create_plan с expected_revision=0. "
    "Никогда не возвращай expected_revision=1 для первого create_plan: 1 — это "
    "будущая ревизия после применения, а не expected_revision. "
    "Для уже существующего плана используй revise_plan/ask_user/complete_plan/"
    "fail_plan и expected_revision, равный текущему plan.revision. "
    "Не создавай циклы. Решения: create_plan, revise_plan, ask_user, "
    "complete_plan, fail_plan."
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE system_llm_roles SET rules = :new_rules "
            "WHERE role_type = 'planner' AND is_active = true "
            "AND rules = :current_rules"
        ),
        {"new_rules": _STRENGTHENED_RULES, "current_rules": _CURRENT_RULES},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE system_llm_roles SET rules = :current_rules "
            "WHERE role_type = 'planner' AND is_active = true "
            "AND rules = :new_rules"
        ),
        {"new_rules": _STRENGTHENED_RULES, "current_rules": _CURRENT_RULES},
    )
