"""Allow document-grounded scope proposals without inventing glossary terms."""
from alembic import op

revision = "0180"
down_revision = "0179"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_memory_scope_proposal_term_source", "memory_scope_proposals", type_="check")
    op.create_check_constraint("ck_memory_scope_proposal_term_source", "memory_scope_proposals",
                               "term_candidate_id IS NULL OR glossary_term_id IS NULL")


def downgrade() -> None:
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM memory_scope_proposals WHERE term_candidate_id IS NULL AND glossary_term_id IS NULL)
      THEN RAISE EXCEPTION '0180 downgrade would invalidate document-grounded scope proposals'; END IF;
    END $$;""")
    op.drop_constraint("ck_memory_scope_proposal_term_source", "memory_scope_proposals", type_="check")
    op.create_check_constraint("ck_memory_scope_proposal_term_source", "memory_scope_proposals",
                               "(term_candidate_id IS NULL) <> (glossary_term_id IS NULL)")
