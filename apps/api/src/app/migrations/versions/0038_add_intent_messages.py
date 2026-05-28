"""Add intent_messages to orchestration_settings

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-28

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0038'
down_revision = '0037'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('orchestration_settings', sa.Column('intent_messages', sa.JSON(), nullable=True, comment='Сообщения намерений (i18n)'))


def downgrade():
    op.drop_column('orchestration_settings', 'intent_messages')
