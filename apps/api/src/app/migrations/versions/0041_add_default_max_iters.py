"""Add default_max_iters to platform_settings

Revision ID: 0041
Revises: 0040
Create Date: 2026-05-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0041'
down_revision = '0040'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'platform_settings',
        sa.Column(
            'default_max_iters',
            sa.Integer(),
            nullable=True,
            comment='Default max planner iterations when execution limits do not provide a value',
        ),
    )
    op.execute("UPDATE platform_settings SET default_max_iters = 25 WHERE default_max_iters IS NULL")


def downgrade():
    op.drop_column('platform_settings', 'default_max_iters')
