"""Add prompt_labels to orchestration_settings

Revision ID: 0040
Revises: 0039
Create Date: 2026-05-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0040'
down_revision = '0039'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orchestration_settings', sa.Column('prompt_labels', sa.JSON(), nullable=True, comment='Лейблы промптов (i18n)'))


def downgrade():
    op.drop_column('orchestration_settings', 'prompt_labels')
