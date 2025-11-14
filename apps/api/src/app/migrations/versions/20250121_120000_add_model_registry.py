# app/migrations/versions/20250121_120000_add_model_registry.py
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20250121_120000"
down_revision = "20250118_100007"
branch_labels = None
depends_on = ("20250102_120000",)


def upgrade():
    # Create model_registry table
    op.create_table(
        'model_registry',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('model', sa.String(255), nullable=False, unique=True),
        sa.Column('version', sa.String(50), nullable=False),
        sa.Column('modality', sa.String(20), nullable=False),  # text|image|layout|table|rerank
        sa.Column('state', sa.String(20), nullable=False, server_default='active'),  # active|archived|retired|disabled
        sa.Column('vector_dim', sa.Integer(), nullable=True),
        sa.Column('path', sa.String(500), nullable=False),
        sa.Column('default_for_new', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    
    # Create indexes for model_registry
    op.create_index('ix_model_registry_model', 'model_registry', ['model'])
    op.create_index('ix_model_registry_state', 'model_registry', ['state'])
    op.create_index('ix_model_registry_modality', 'model_registry', ['modality'])
    op.create_index('ix_model_registry_default_for_new', 'model_registry', ['default_for_new'])
    
    # Extend tenants table with model-related fields
    op.add_column('tenants', sa.Column('embed_models', postgresql.ARRAY(sa.String()), nullable=True))
    op.add_column('tenants', sa.Column('rerank_model', sa.String(255), nullable=True))
    op.add_column('tenants', sa.Column('ocr', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('tenants', sa.Column('layout', sa.Boolean(), nullable=False, server_default='false'))
    
    # Add foreign key constraint for rerank_model
    op.create_foreign_key(
        'fk_tenants_rerank_model_model_registry',
        'tenants', 'model_registry',
        ['rerank_model'], ['model'],
        ondelete='SET NULL'
    )


def downgrade():
    # Drop foreign key constraint
    op.drop_constraint('fk_tenants_rerank_model_model_registry', 'tenants', type_='foreignkey')
    
    # Drop columns from tenants table
    op.drop_column('tenants', 'layout')
    op.drop_column('tenants', 'ocr')
    op.drop_column('tenants', 'rerank_model')
    op.drop_column('tenants', 'embed_models')
    
    # Drop indexes
    op.drop_index('ix_model_registry_default_for_new', 'model_registry')
    op.drop_index('ix_model_registry_modality', 'model_registry')
    op.drop_index('ix_model_registry_state', 'model_registry')
    op.drop_index('ix_model_registry_model', 'model_registry')
    
    # Drop model_registry table
    op.drop_table('model_registry')
