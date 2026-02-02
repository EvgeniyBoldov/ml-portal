"""Add recommended_version_id to prompts table."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0057'
down_revision = '0056'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add recommended_version_id column to prompts table
    op.add_column('prompts', sa.Column(
        'recommended_version_id',
        postgresql.UUID(as_uuid=True),
        nullable=True
    ))
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_prompts_recommended_version_id',
        'prompts',
        'prompt_versions',
        ['recommended_version_id'],
        ['id'],
        ondelete='SET NULL'
    )
    
    # Add index for performance
    op.create_index(
        'ix_prompts_recommended_version_id',
        'prompts',
        ['recommended_version_id']
    )


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_prompts_recommended_version_id', table_name='prompts')
    
    # Drop foreign key
    op.drop_constraint('fk_prompts_recommended_version_id', 'prompts', type_='foreignkey')
    
    # Drop column
    op.drop_column('prompts', 'recommended_version_id')
