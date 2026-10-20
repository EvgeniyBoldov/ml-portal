"""Align the known planner output policy with its three runtime branches."""
from alembic import op
import sqlalchemy as sa

revision = "0198"
down_revision = "0197"
branch_labels = None
depends_on = None

OLD = "Верни только PlannerStep JSON по добавленной runtime schema: kind=proposal с полной IterationProposal либо kind=tool_call для памяти. В synthesis_brief задай цель ответа, подтверждённые результаты и оставшиеся ограничения; не описывай невыполненную работу как готовую или автоматически продолжающуюся."
NEW = "Верни только PlannerStep JSON по добавленной runtime schema: kind=proposal для плана, kind=tool_call для доступного инструмента или kind=interaction для блокирующего вопроса пользователю. В synthesis_brief задай цель ответа, подтверждённые результаты и оставшиеся ограничения; не описывай невыполненную работу как готовую или автоматически продолжающуюся."
BACKUP = "_planner_output_backup_0198"


def upgrade() -> None:
    op.get_bind().execute(sa.text("""UPDATE system_llm_roles
        SET output_requirements=:new,
            extras=jsonb_set(COALESCE(extras,'{}'::jsonb), ARRAY[:key], to_jsonb(CAST(:old AS text))),
            updated_at=now()
        WHERE role_type='planner' AND output_requirements=:old
          AND NOT (COALESCE(extras,'{}'::jsonb) ? :key)"""),
        {"old": OLD, "new": NEW, "key": BACKUP})


def downgrade() -> None:
    op.get_bind().execute(sa.text("""UPDATE system_llm_roles
        SET output_requirements=:old, extras=extras-:key, updated_at=now()
        WHERE role_type='planner' AND output_requirements=:new AND extras->>:key=:old"""),
        {"old": OLD, "new": NEW, "key": BACKUP})
