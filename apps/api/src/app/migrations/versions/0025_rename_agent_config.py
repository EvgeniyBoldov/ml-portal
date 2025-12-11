"""Rename agent config

Revision ID: 0025_rename_agent_config
Revises: 0024_create_agents_table
Create Date: 2025-12-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0025_rename_agent_config'
down_revision: Union[str, None] = '0024_create_agents_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('agents', 'model_config', new_column_name='generation_config')


def downgrade() -> None:
    op.alter_column('agents', 'generation_config', new_column_name='model_config')
