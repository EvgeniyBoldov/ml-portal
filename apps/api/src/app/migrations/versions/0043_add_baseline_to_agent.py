"""add baseline to agent

Revision ID: 0043
Revises: 0042
Create Date: 2026-01-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0043'
down_revision = '0042'
branch_labels = None
depends_on = None


def upgrade():
    # Add baseline_prompt_slug column (nullable for now)
    op.add_column(
        'agents',
        sa.Column('baseline_prompt_slug', sa.String(255), nullable=True)
    )
    
    # Add foreign key constraint
    # Note: We don't enforce type='baseline' at DB level, will be checked in service layer
    op.create_foreign_key(
        'fk_agents_baseline_prompt_slug',
        'agents',
        'prompts',
        ['baseline_prompt_slug'],
        ['slug'],
        ondelete='SET NULL'
    )
    
    # Add index for performance
    op.create_index(
        'ix_agents_baseline_prompt_slug',
        'agents',
        ['baseline_prompt_slug']
    )


def downgrade():
    op.drop_index('ix_agents_baseline_prompt_slug', table_name='agents')
    op.drop_constraint('fk_agents_baseline_prompt_slug', 'agents', type_='foreignkey')
    op.drop_column('agents', 'baseline_prompt_slug')
