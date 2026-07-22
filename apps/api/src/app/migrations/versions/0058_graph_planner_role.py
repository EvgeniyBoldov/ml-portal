"""Move the active planner role to the persisted graph contract."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE system_llm_roles
        SET mission = :mission,
            rules = :rules,
            output_requirements = :requirements
        WHERE role_type = 'planner' AND is_active = true
    """), {
        "mission": "Построй или скорректируй полный граф задач для оркестратора. Не вызывай агентов и не отвечай пользователю.",
        "rules": "Верни мутацию графа. Используй только available_agents; expected_revision обязан совпадать с plan.revision; не создавай циклы. Решения: create_plan, revise_plan, ask_user, complete_plan, fail_plan.",
        "requirements": "Строгий JSON: decision, expected_revision, rationale, tasks, remove_task_ids, question, answer_brief, failure_reason, trigger.",
    })


def downgrade() -> None:
    raise RuntimeError("Planner graph contract is irreversible; restore the role explicitly if required")
