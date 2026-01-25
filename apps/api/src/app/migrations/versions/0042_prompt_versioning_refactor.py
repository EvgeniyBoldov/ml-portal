"""Prompt versioning refactor: add status, parent_version_id, update type enum

Revision ID: 0042
Revises: 0041
Create Date: 2025-01-24

Changes:
- Add 'status' column (draft/active/archived) with index
- Add 'parent_version_id' FK for version history tracking
- Update 'type' column values: chat/agent/task -> prompt/baseline
- Migrate existing is_active=True to status='active', is_active=False to status='archived'
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0042'
down_revision = '0041_agent_permissions_system'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add status column
    op.add_column(
        'prompts',
        sa.Column('status', sa.String(20), nullable=True)
    )
    
    # Add parent_version_id column
    op.add_column(
        'prompts',
        sa.Column(
            'parent_version_id', 
            postgresql.UUID(as_uuid=True), 
            sa.ForeignKey('prompts.id', ondelete='SET NULL'),
            nullable=True
        )
    )
    
    # Migrate existing data: is_active=True -> status='active', else 'archived'
    op.execute("""
        UPDATE prompts 
        SET status = CASE 
            WHEN is_active = true THEN 'active'
            ELSE 'archived'
        END
    """)
    
    # Make status non-nullable after migration
    op.alter_column('prompts', 'status', nullable=False)
    
    # Create index on status
    op.create_index('ix_prompts_status', 'prompts', ['status'])
    
    # Update type values: map old types to new types
    # chat, agent, task, system -> prompt (default)
    # Keep 'baseline' if it exists
    op.execute("""
        UPDATE prompts 
        SET type = CASE 
            WHEN type = 'baseline' THEN 'baseline'
            ELSE 'prompt'
        END
    """)


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_prompts_status', table_name='prompts')
    
    # Restore is_active from status
    op.execute("""
        UPDATE prompts 
        SET is_active = CASE 
            WHEN status = 'active' THEN true
            ELSE false
        END
    """)
    
    # Restore type values
    op.execute("""
        UPDATE prompts 
        SET type = 'chat'
        WHERE type = 'prompt'
    """)
    
    # Drop columns
    op.drop_column('prompts', 'parent_version_id')
    op.drop_column('prompts', 'status')
