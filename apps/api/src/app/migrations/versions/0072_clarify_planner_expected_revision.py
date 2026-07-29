"""Clarify the default planner revision contract.

Only the untouched legacy system default is updated.  Administrator-edited
planner prompts remain authoritative and are not changed by this migration.
"""

import sqlalchemy as sa
from alembic import op


revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


_LEGACY_RULES = (
    "Верни мутацию графа. Используй только available_agents; "
    "expected_revision обязан совпадать с plan.revision; не создавай циклы. "
    "Решения: create_plan, revise_plan, ask_user, complete_plan, fail_plan."
)
_CLARIFIED_RULES = (
    "Верни мутацию графа. Используй только available_agents; "
    "expected_revision — текущая plan.revision ДО применения мутации, "
    "а не будущая ревизия. Для первого create_plan при plan.revision=0 "
    "всегда верни expected_revision=0. Не создавай циклы. "
    "Решения: create_plan, revise_plan, ask_user, complete_plan, fail_plan."
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE system_llm_roles SET rules = :new_rules "
            "WHERE role_type = 'planner' AND is_active = true "
            "AND rules = :legacy_rules"
        ),
        {"new_rules": _CLARIFIED_RULES, "legacy_rules": _LEGACY_RULES},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE system_llm_roles SET rules = :legacy_rules "
            "WHERE role_type = 'planner' AND is_active = true "
            "AND rules = :new_rules"
        ),
        {"new_rules": _CLARIFIED_RULES, "legacy_rules": _LEGACY_RULES},
    )
