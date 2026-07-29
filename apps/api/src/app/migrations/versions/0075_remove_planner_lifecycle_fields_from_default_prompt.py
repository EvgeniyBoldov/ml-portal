"""Keep planner lifecycle fields runtime-owned in the untouched default role."""

import sqlalchemy as sa
from alembic import op


revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


_OLD_RULES = (
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
_OLD_REQUIREMENTS = (
    "Строгий JSON: decision, expected_revision, rationale, tasks, remove_task_ids, "
    "question, answer_brief, failure_reason, trigger."
)
_NEW_RULES = (
    "Верни только смысловую мутацию графа. Runtime сам определяет initial/replan, "
    "ревизию, trigger и lifecycle. Для работы с графом используй action=apply_graph; "
    "для запроса данных — ask_user; при достижении цели — complete; при невозможности "
    "продолжить — fail. Используй executor только из available_agents. Не создавай циклы."
)
_NEW_REQUIREMENTS = (
    "Строгий JSON: action, tasks, remove_task_ids, question, answer_brief, failure_reason. "
    "Не возвращай revision, expected_revision, trigger, goal, id или rationale."
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE system_llm_roles SET rules = :new_rules, output_requirements = :new_requirements "
            "WHERE role_type = 'planner' AND is_active = true "
            "AND rules = :old_rules AND output_requirements = :old_requirements"
        ),
        {
            "new_rules": _NEW_RULES,
            "new_requirements": _NEW_REQUIREMENTS,
            "old_rules": _OLD_RULES,
            "old_requirements": _OLD_REQUIREMENTS,
        },
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE system_llm_roles SET rules = :old_rules, output_requirements = :old_requirements "
            "WHERE role_type = 'planner' AND is_active = true "
            "AND rules = :new_rules AND output_requirements = :new_requirements"
        ),
        {
            "new_rules": _NEW_RULES,
            "new_requirements": _NEW_REQUIREMENTS,
            "old_rules": _OLD_RULES,
            "old_requirements": _OLD_REQUIREMENTS,
        },
    )
