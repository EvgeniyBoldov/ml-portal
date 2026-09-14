"""Remove the retired project-fact persistence model.

Revision ID: 0117
Revises: 0116
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0117"
down_revision = "0116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Project knowledge is now represented exclusively by source-backed
    # MemoryItems. Delete the old rows; fact_observations follows through its
    # ON DELETE CASCADE foreign key.
    op.execute(sa.text("DELETE FROM facts WHERE scope = 'project'"))
    op.drop_constraint("ck_facts_scope", "facts", type_="check")
    op.create_check_constraint("ck_facts_scope", "facts", "scope IN ('user', 'tenant')")
    op.drop_index("ix_facts_project_id", table_name="facts")
    op.drop_constraint("fk_facts_project_id", "facts", type_="foreignkey")
    op.drop_column("facts", "project_id")

    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET mission = 'Семантически нормализуй user, tenant и glossary-кандидаты без создания новых сведений.',
            rules = 'Используй candidates и current_facts. Для user/tenant объединяй смысловые дубли после точных совпадений. Для glossary нормализуй термин и алиасы. Всегда указывай source_candidate_indexes.',
            updated_at = now()
        WHERE role_type = 'fact_compactor'
    """))


def downgrade() -> None:
    # The deleted legacy rows intentionally cannot be reconstructed.
    pass
