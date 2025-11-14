# app/migrations/versions/20250113_170000_add_rag_ingest_pipeline_tables.py
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20250113_170000"
down_revision = "20250103_150001"
branch_labels = None
depends_on = None

def upgrade():
    # 1.1. Таблица sources (если уже есть — дополнить полями)
    op.create_table(
        'sources',
        sa.Column('source_id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('meta', postgresql.JSONB(), nullable=True),
        sa.CheckConstraint(
            "status IN ('uploaded','normalized','chunked','embedding','ready','failed','reindexing')",
            name='ck_sources_status'
        )
    )
    
    # 1.2. Таблица chunks
    op.create_table(
        'chunks',
        sa.Column('chunk_id', sa.Text(), primary_key=True),
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('page', sa.Integer(), nullable=True),
        sa.Column('offset', sa.Integer(), nullable=False),
        sa.Column('length', sa.Integer(), nullable=False),
        sa.Column('lang', sa.Text(), nullable=True),
        sa.Column('hash', sa.Text(), nullable=False),
        sa.Column('meta', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['source_id'], ['sources.source_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('source_id', 'offset', name='uq_chunks_source_offset')
    )
    
    # 1.3. Таблица emb_status — прогресс по моделям
    op.create_table(
        'emb_status',
        sa.Column('source_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model_alias', sa.Text(), nullable=False),
        sa.Column('done_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('total_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('model_version', sa.Text(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['source_id'], ['sources.source_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('source_id', 'model_alias')
    )
    
    # 1.4. model_registry — alias→version (создаём, только если нет более новой схемы)
    from sqlalchemy import inspect as _inspect
    bind = op.get_bind()
    inspector = _inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if 'model_registry' not in existing_tables:
        op.create_table(
            'model_registry',
            sa.Column('model_alias', sa.Text(), primary_key=True),
            sa.Column('model_version', sa.Text(), nullable=False),
            sa.Column('dim', sa.Integer(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)
        )
    
    # Индексы для производительности
    op.create_index('ix_sources_status', 'sources', ['status'])
    op.create_index('ix_sources_updated_at', 'sources', ['updated_at'])
    op.create_index('ix_chunks_source_id', 'chunks', ['source_id'])
    op.create_index('ix_chunks_hash', 'chunks', ['hash'])
    op.create_index('ix_emb_status_source_id', 'emb_status', ['source_id'])
    op.create_index('ix_emb_status_model_alias', 'emb_status', ['model_alias'])

def downgrade():
    # Удаляем таблицы в обратном порядке
    op.drop_index('ix_emb_status_model_alias', 'emb_status')
    op.drop_index('ix_emb_status_source_id', 'emb_status')
    op.drop_index('ix_chunks_hash', 'chunks')
    op.drop_index('ix_chunks_source_id', 'chunks')
    op.drop_index('ix_sources_updated_at', 'sources')
    op.drop_index('ix_sources_status', 'sources')
    
    op.drop_table('model_registry')
    op.drop_table('emb_status')
    op.drop_table('chunks')
    op.drop_table('sources')
