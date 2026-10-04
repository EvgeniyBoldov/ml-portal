"""Use team/project applicability and project service types.

Revision ID: 0179
Revises: 0178
"""
from alembic import op
import sqlalchemy as sa

revision = "0179"
down_revision = "0178"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A concrete product cannot be silently reclassified as a customer project.
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM memory_scopes WHERE scope_type = 'product' AND NOT is_all)
         OR EXISTS (SELECT 1 FROM memory_scope_proposals WHERE scope_type = 'product')
      THEN RAISE EXCEPTION 'Classify concrete product scopes as project types before applying 0179';
      END IF;
    END $$;""")
    # Fold the obsolete universal product marker into the universal project
    # marker, preserving references and avoiding duplicate composite keys.
    op.execute("""INSERT INTO memory_scopes (id, scope_type, key, name, aliases, is_all)
        VALUES (gen_random_uuid(), 'project', 'project.all', 'Все проекты', '{}', true)
        ON CONFLICT (scope_type, key) DO NOTHING""")
    for table, columns in (
        ("memory_claim_scopes", "claim_id, scope_id"),
        ("document_memory_scopes", "document_id, scope_id, method"),
        ("memory_candidate_scopes", "id, candidate_id, scope_id, role, status, confidence, rationale, method"),
    ):
        selected = columns.replace("scope_id", "(SELECT id FROM memory_scopes WHERE key = 'project.all')")
        if table == "memory_candidate_scopes":
            selected = selected.replace("id, candidate_id", "gen_random_uuid(), candidate_id", 1)
        op.execute(f"""INSERT INTO {table} ({columns}) SELECT {selected} FROM {table}
            WHERE scope_id IN (SELECT id FROM memory_scopes WHERE scope_type = 'product')
            ON CONFLICT DO NOTHING""")
        op.execute(f"DELETE FROM {table} WHERE scope_id IN (SELECT id FROM memory_scopes WHERE scope_type = 'product')")
    # There are no concrete products; product.all has no lexical meaning.
    op.execute("DELETE FROM memory_scope_glossary_terms WHERE scope_id IN (SELECT id FROM memory_scopes WHERE scope_type = 'product')")
    op.execute("DELETE FROM memory_scopes WHERE scope_type = 'product'")
    op.drop_constraint("ck_memory_scopes_all_key", "memory_scopes", type_="check")
    op.drop_constraint("ck_memory_scopes_project_type", "memory_scopes", type_="check")
    op.execute("ALTER TYPE memoryscopetype RENAME TO memoryscopetype_old")
    op.execute("CREATE TYPE memoryscopetype AS ENUM ('project', 'team')")
    op.execute("ALTER TABLE memory_scopes ALTER COLUMN scope_type TYPE memoryscopetype USING scope_type::text::memoryscopetype")
    op.execute("DROP TYPE memoryscopetype_old")
    op.create_check_constraint("ck_memory_scopes_all_key", "memory_scopes", "key LIKE scope_type::text || '.%' AND ((is_all AND key = scope_type::text || '.all') OR (NOT is_all AND key <> scope_type::text || '.all'))")
    op.create_check_constraint("ck_memory_scopes_project_type", "memory_scopes", "project_id IS NULL OR (scope_type = 'project' AND NOT is_all)")
    op.drop_constraint("ck_memory_scope_proposal_type", "memory_scope_proposals", type_="check")
    op.create_check_constraint("ck_memory_scope_proposal_type", "memory_scope_proposals", "scope_type IN ('project', 'team')")
    for table in ("projects", "memory_scopes", "memory_scope_proposals"):
        op.add_column(table, sa.Column("project_type", sa.String(80), nullable=True))
    op.create_check_constraint("ck_memory_scope_project_subtype", "memory_scopes", "project_type IS NULL OR (scope_type = 'project' AND NOT is_all)")
    op.create_check_constraint("ck_memory_scope_proposal_project_subtype", "memory_scope_proposals", "project_type IS NULL OR scope_type = 'project'")


def downgrade() -> None:
    op.drop_constraint("ck_memory_scope_proposal_project_subtype", "memory_scope_proposals", type_="check")
    op.drop_constraint("ck_memory_scope_project_subtype", "memory_scopes", type_="check")
    for table in ("projects", "memory_scopes", "memory_scope_proposals"):
        op.drop_column(table, "project_type")
    op.execute("ALTER TYPE memoryscopetype ADD VALUE IF NOT EXISTS 'product'")
    op.drop_constraint("ck_memory_scope_proposal_type", "memory_scope_proposals", type_="check")
    op.create_check_constraint("ck_memory_scope_proposal_type", "memory_scope_proposals", "scope_type IN ('product', 'project', 'team')")
