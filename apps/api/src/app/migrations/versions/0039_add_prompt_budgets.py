"""Add prompt_budgets to orchestration_settings

Revision ID: 0039
Revises: 0038
Create Date: 2026-05-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0039'
down_revision = '0038'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orchestration_settings', sa.Column('prompt_budgets', sa.JSON(), nullable=True, comment='Бюджеты промптов (magic numbers)'))


def downgrade():
    op.drop_column('orchestration_settings', 'prompt_budgets')
