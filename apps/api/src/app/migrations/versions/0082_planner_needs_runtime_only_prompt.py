"""Make executor-discovered needs explicit in the untouched planner default."""

import sqlalchemy as sa
from alembic import op


revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


_OLD_RULES = (
    "Верни только смысловую мутацию графа. Runtime сам определяет initial/replan, "
    "ревизию, trigger и lifecycle. Для работы с графом используй action=apply_graph; "
    "для запроса данных — ask_user; при достижении цели — complete; при невозможности "
    "продолжить — fail. Используй executor только из available_agents. Не создавай циклы."
)
_NEW_RULES = (
    "Верни только смысловую мутацию графа. Runtime сам определяет initial/replan, "
    "ревизию, trigger и lifecycle. Для работы с графом используй action=apply_graph; "
    "для запроса данных — ask_user; при достижении цели — complete; при невозможности "
    "продолжить — fail. Используй executor только из available_agents. Не создавай циклы. "
    "Никогда не создавай поле needs: needs объявляет только исполнитель после реальной "
    "попытки выполнения. Для каждого pending need добавь задачу-производитель с "
    "expected_outputs, содержащим тот же key, и свяжи её с ожидающей задачей через "
    "depends_on; либо используй ask_user с одним конкретным вопросом; либо fail."
)


def upgrade() -> None:
    """Update only the untouched mandatory planner default, never custom roles."""
    op.get_bind().execute(
        sa.text(
            "UPDATE system_llm_roles SET rules = :new_rules "
            "WHERE role_type = 'planner' AND is_active = true AND rules = :old_rules"
        ),
        {"old_rules": _OLD_RULES, "new_rules": _NEW_RULES},
    )


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE system_llm_roles SET rules = :old_rules "
            "WHERE role_type = 'planner' AND is_active = true AND rules = :new_rules"
        ),
        {"old_rules": _OLD_RULES, "new_rules": _NEW_RULES},
    )
