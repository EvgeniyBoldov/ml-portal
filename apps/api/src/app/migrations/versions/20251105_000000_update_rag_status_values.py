"""Update RAG status values and add celery tracking fields

Revision ID: 20251105_000000
Revises: 20251029_102113
Create Date: 2025-11-05 00:00:00

"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251105_000000"
down_revision = "20250122_120000"  # Latest rag_statuses migration
branch_labels = None
depends_on = None


def upgrade():
    """
    Update RAG status system:
    1. Update status values: ok→completed, running→processing, error→failed
    2. Add celery_task_id, attempt, max_attempts fields
    """
    
    # Add new columns to rag_statuses table
    op.add_column('rag_statuses', sa.Column('celery_task_id', sa.String(255), nullable=True))
    op.add_column('rag_statuses', sa.Column('attempt', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('rag_statuses', sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='2'))
    
    # Create index for celery_task_id
    op.create_index('ix_rag_statuses_celery_task_id', 'rag_statuses', ['celery_task_id'])
    
    # Update existing status values
    # Note: Using raw SQL for data migration
    op.execute("""
        UPDATE rag_statuses 
        SET status = CASE 
            WHEN status = 'ok' THEN 'completed'
            WHEN status = 'running' THEN 'processing'
            WHEN status = 'error' THEN 'failed'
            WHEN status = 'pending' THEN 'pending'
            ELSE status
        END
        WHERE status IN ('ok', 'running', 'error', 'pending')
    """)
    
    # Note: We don't add a CHECK constraint because we want flexibility
    # The application layer (RAGStatusManager) will enforce valid transitions


def downgrade():
    """
    Revert changes:
    1. Revert status values: completed→ok, processing→running, failed→error
    2. Remove celery_task_id, attempt, max_attempts fields
    """
    
    # Revert status values
    op.execute("""
        UPDATE rag_statuses 
        SET status = CASE 
            WHEN status = 'completed' THEN 'ok'
            WHEN status = 'processing' THEN 'running'
            WHEN status = 'failed' THEN 'error'
            WHEN status = 'pending' THEN 'pending'
            ELSE status
        END
        WHERE status IN ('completed', 'processing', 'failed', 'pending')
    """)
    
    # Remove index
    op.drop_index('ix_rag_statuses_celery_task_id', 'rag_statuses')
    
    # Remove columns
    op.drop_column('rag_statuses', 'max_attempts')
    op.drop_column('rag_statuses', 'attempt')
    op.drop_column('rag_statuses', 'celery_task_id')
