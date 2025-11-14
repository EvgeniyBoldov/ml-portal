# app/migrations/versions/20250122_120000_add_rag_statuses.py
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20250122_120000"
down_revision = "20250121_120000"  # Latest migration from the list
branch_labels = None
depends_on = None


def upgrade():
    # Create rag_statuses table
    op.create_table(
        'rag_statuses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('doc_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('node_type', sa.String(20), nullable=False),  # 'pipeline' | 'embedding'
        sa.Column('node_key', sa.String(100), nullable=False),  # 'upload'|'extract'|'chunk'|'index' OR model_id
        sa.Column('status', sa.String(20), nullable=False),  # 'pending'|'running'|'ok'|'error'
        sa.Column('model_version', sa.String(50), nullable=True),
        sa.Column('modality', sa.String(20), nullable=True),  # 'text'|'image'
        sa.Column('error_short', sa.Text(), nullable=True),
        sa.Column('metrics_json', postgresql.JSONB(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['doc_id'], ['ragdocuments.id'], ondelete='CASCADE'),
    )
    
    # Create indexes for rag_statuses
    op.create_index('ix_rag_statuses_doc_id', 'rag_statuses', ['doc_id'])
    op.create_index('ix_rag_statuses_status', 'rag_statuses', ['status'])
    op.create_index('ix_rag_statuses_node_type', 'rag_statuses', ['node_type'])
    op.create_index('ix_rag_statuses_updated_at', 'rag_statuses', ['updated_at'])
    
    # Create unique constraint
    op.create_unique_constraint('uq_rag_statuses_doc_node', 'rag_statuses', ['doc_id', 'node_type', 'node_key'])
    
    # Add new columns to ragdocuments table
    op.add_column('ragdocuments', sa.Column('agg_status', sa.String(20), nullable=True))
    op.add_column('ragdocuments', sa.Column('agg_details_json', postgresql.JSONB(), nullable=True))
    
    # Create index for agg_status
    op.create_index('ix_ragdocuments_agg_status', 'ragdocuments', ['agg_status'])


def downgrade():
    # Remove indexes
    op.drop_index('ix_ragdocuments_agg_status', 'ragdocuments')
    op.drop_index('ix_rag_statuses_updated_at', 'rag_statuses')
    op.drop_index('ix_rag_statuses_node_type', 'rag_statuses')
    op.drop_index('ix_rag_statuses_status', 'rag_statuses')
    op.drop_index('ix_rag_statuses_doc_id', 'rag_statuses')
    
    # Remove columns from ragdocuments
    op.drop_column('ragdocuments', 'agg_details_json')
    op.drop_column('ragdocuments', 'agg_status')
    
    # Drop table
    op.drop_table('rag_statuses')
