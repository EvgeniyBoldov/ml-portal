"""Do not promote legacy project glossary definitions to global.

Revision ID: 0147
Revises: 0146
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0147"
down_revision = "0146"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The legacy document extractor wrote project terms as scope=global while
    # retaining project_id.  project_id is the stronger migration evidence;
    # otherwise P0 would accidentally publish a project-only definition as a
    # confirmed global meaning.
    op.execute(sa.text("""
        UPDATE glossary_meanings meaning
        SET scope_candidate = 'project',
            resolution_status = 'resolved',
            resolution_rationale = 'Backfilled as project-scoped because the legacy glossary entry has project_id.',
            updated_at = now()
        FROM glossary_entries entry
        WHERE entry.id = meaning.legacy_glossary_entry_id
          AND entry.project_id IS NOT NULL
          AND meaning.resolution_method = 'migration'
    """))


def downgrade() -> None:
    # The previous interpretation cannot be restored safely: a global legacy
    # row with project_id is ambiguous by definition.
    pass
