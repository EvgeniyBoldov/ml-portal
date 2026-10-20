"""Align the stored preflight prompt with the metadata-only datastore input."""
from alembic import op
import sqlalchemy as sa

revision = "0196"
down_revision = "0195"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""UPDATE system_llm_roles
        SET rules = replace(rules, :old, :new), updated_at = now()
        WHERE role_type = 'turn_preflight' AND is_active IS TRUE
          AND strpos(rules, :old) > 0
    """).bindparams(old="available_artifacts содержит паспорта доступных вложений",
                    new="datastore.items содержит паспорта доступных вложений с kind=file"))


def downgrade() -> None:
    op.execute(sa.text("""UPDATE system_llm_roles
        SET rules = replace(rules, :new, :old), updated_at = now()
        WHERE role_type = 'turn_preflight' AND is_active IS TRUE
          AND strpos(rules, :new) > 0
    """).bindparams(old="available_artifacts содержит паспорта доступных вложений",
                    new="datastore.items содержит паспорта доступных вложений с kind=file"))
