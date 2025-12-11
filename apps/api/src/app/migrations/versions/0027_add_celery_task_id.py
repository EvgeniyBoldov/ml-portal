"""Add celery_task_id to rag_statuses for task cancellation

Revision ID: 0027
Revises: 0026
Create Date: 2024-12-11
"""
from alembic import op
import sqlalchemy as sa

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'rag_statuses',
        sa.Column('celery_task_id', sa.String(50), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('rag_statuses', 'celery_task_id')
