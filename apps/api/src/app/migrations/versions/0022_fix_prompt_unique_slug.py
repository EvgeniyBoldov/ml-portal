"""Fix prompt unique slug

Revision ID: 0022_fix_prompt_unique_slug
Revises: 0021_seed_default_prompts
Create Date: 2025-11-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0022_fix_prompt_unique_slug'
down_revision: Union[str, None] = '0021_seed_default_prompts'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the unique index on slug
    op.drop_index('ix_prompts_slug', table_name='prompts')
    
    # Create a non-unique index on slug
    op.create_index(op.f('ix_prompts_slug'), 'prompts', ['slug'], unique=False)
    
    # Add a composite unique constraint on (slug, version)
    op.create_unique_constraint('uix_slug_version', 'prompts', ['slug', 'version'])


def downgrade() -> None:
    # Drop the composite unique constraint
    op.drop_constraint('uix_slug_version', 'prompts', type_='unique')
    
    # Drop the non-unique index
    op.drop_index(op.f('ix_prompts_slug'), table_name='prompts')
    
    # Re-create the unique index on slug
    op.create_index('ix_prompts_slug', 'prompts', ['slug'], unique=True)
