"""Add tool_use_guard to orchestration_settings

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0036'
down_revision = '0035'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orchestration_settings', sa.Column('tool_use_guard', sa.String(2000), nullable=True, comment='Policy text for tool use (MANDATORY RULES)'))


def downgrade():
    op.drop_column('orchestration_settings', 'tool_use_guard')
