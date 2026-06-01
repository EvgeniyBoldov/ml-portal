"""Add sandbox branch artifacts columns

Revision ID: 0042
Revises: 0041
Create Date: 2026-06-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0042'
down_revision = '0041'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'sandbox_branches',
        sa.Column('facts_artifact_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        'sandbox_branches',
        sa.Column('summary_artifact_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        'sandbox_branches',
        sa.Column('artifacts_updated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column('sandbox_branches', 'facts_artifact_json', server_default=None)
    op.alter_column('sandbox_branches', 'summary_artifact_json', server_default=None)


def downgrade():
    op.drop_column('sandbox_branches', 'artifacts_updated_at')
    op.drop_column('sandbox_branches', 'summary_artifact_json')
    op.drop_column('sandbox_branches', 'facts_artifact_json')
