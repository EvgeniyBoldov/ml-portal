"""Add recommended_version_id to baselines table."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0056'
down_revision = '0055'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add recommended_version_id column to baselines table
    op.add_column('baselines', sa.Column(
        'recommended_version_id',
        postgresql.UUID(as_uuid=True),
        nullable=True
    ))
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_baselines_recommended_version_id',
        'baselines',
        'baseline_versions',
        ['recommended_version_id'],
        ['id'],
        ondelete='SET NULL'
    )
    
    # Add index for performance
    op.create_index(
        'ix_baselines_recommended_version_id',
        'baselines',
        ['recommended_version_id']
    )


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_baselines_recommended_version_id', table_name='baselines')
    
    # Drop foreign key
    op.drop_constraint('fk_baselines_recommended_version_id', 'baselines', type_='foreignkey')
    
    # Drop column
    op.drop_column('baselines', 'recommended_version_id')
