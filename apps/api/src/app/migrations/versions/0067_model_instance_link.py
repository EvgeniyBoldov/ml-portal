"""Model-Instance link: remove base_url/api_key_ref, add instance_id FK; add category to tool_instances

Revision ID: 0067
Revises: 0066
Create Date: 2026-02-11

Changes:
- models: drop base_url, api_key_ref columns
- models: add instance_id FK to tool_instances
- tool_instances: add category column (tag for filtering)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = '0067'
down_revision: Union[str, None] = '0066'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add category to tool_instances
    op.add_column(
        'tool_instances',
        sa.Column('category', sa.String(50), nullable=True, comment='Instance category tag for filtering')
    )
    op.create_index('ix_tool_instances_category', 'tool_instances', ['category'])

    # 2. Add instance_id FK to models (nullable, will be populated later)
    op.add_column(
        'models',
        sa.Column('instance_id', UUID(as_uuid=True), nullable=True, comment='FK to tool_instances (provider connection)')
    )
    op.create_index('ix_models_instance_id', 'models', ['instance_id'])
    op.create_foreign_key(
        'fk_models_instance_id',
        'models', 'tool_instances',
        ['instance_id'], ['id'],
        ondelete='SET NULL'
    )

    # 3. Drop base_url and api_key_ref from models
    op.drop_column('models', 'base_url')
    op.drop_column('models', 'api_key_ref')


def downgrade() -> None:
    # 1. Re-add base_url and api_key_ref
    op.add_column(
        'models',
        sa.Column('base_url', sa.String(500), nullable=True, comment='API base URL')
    )
    op.add_column(
        'models',
        sa.Column('api_key_ref', sa.String(255), nullable=True, comment='Reference to secret (not raw key)')
    )

    # 2. Drop instance_id FK
    op.drop_constraint('fk_models_instance_id', 'models', type_='foreignkey')
    op.drop_index('ix_models_instance_id', table_name='models')
    op.drop_column('models', 'instance_id')

    # 3. Drop category from tool_instances
    op.drop_index('ix_tool_instances_category', table_name='tool_instances')
    op.drop_column('tool_instances', 'category')
