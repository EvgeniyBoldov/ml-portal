"""Make approved terminology independent of source scopes and lifecycle."""
import json

from alembic import op
import sqlalchemy as sa

from app.runtime.memory.shadow_study_prompts import SHADOW_DOCUMENT_STUDY_PROMPT
from app.services.v3_role_defaults import DOCUMENT_MEMORY_EXTRACTOR_V1

revision = "0181"
down_revision = "0180"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("fk_glossary_terms_approved_candidate", "glossary_terms", type_="foreignkey")
    op.alter_column("glossary_terms", "approved_candidate_id", existing_type=sa.UUID(), nullable=True)
    op.create_foreign_key("fk_glossary_terms_approved_candidate", "glossary_terms",
                          "memory_extraction_candidates", ["approved_candidate_id"], ["id"], ondelete="SET NULL")
    op.get_bind().execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = :rules, extras = jsonb_set(COALESCE(extras, '{}'::jsonb),
            '{document_memory_study_prompt}', CAST(:prompt AS jsonb), true)
        WHERE role_type = 'document_memory_extractor'
    """), {"prompt": json.dumps(SHADOW_DOCUMENT_STUDY_PROMPT, ensure_ascii=False),
           "rules": DOCUMENT_MEMORY_EXTRACTOR_V1["rules"]})


def downgrade() -> None:
    op.drop_constraint("fk_glossary_terms_approved_candidate", "glossary_terms", type_="foreignkey")
    op.alter_column("glossary_terms", "approved_candidate_id", existing_type=sa.UUID(), nullable=False)
    op.create_foreign_key("fk_glossary_terms_approved_candidate", "glossary_terms",
                          "memory_extraction_candidates", ["approved_candidate_id"], ["id"], ondelete="CASCADE")
