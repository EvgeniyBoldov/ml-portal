"""Add retry_instruction to orchestration_settings

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0037'
down_revision = '0036'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orchestration_settings', sa.Column('retry_instruction', sa.String(1000), nullable=True, comment='Инструкция для повтора при отсутствии вызова операции'))


def downgrade():
    op.drop_column('orchestration_settings', 'retry_instruction')
