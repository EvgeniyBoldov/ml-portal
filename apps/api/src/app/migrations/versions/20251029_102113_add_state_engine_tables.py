"""Add State Engine tables: jobs, status_history, events_outbox, document_versions

Revision ID: 20251029_102113
Revises: 20250912_104656_add_chat_tags
Create Date: 2025-10-29 10:21:13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20251029_102113'
down_revision = '20250912_104656_add_chat_tags'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =============================================================================
    # document_versions - версионирование документов
    # =============================================================================
    op.create_table(
        'document_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False, comment='SHA256 hash of content'),
        sa.Column('storage_uri', sa.Text(), nullable=False, comment='S3 URI or path'),
        sa.Column('size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        
        sa.ForeignKeyConstraint(['document_id'], ['ragdocuments.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('document_id', 'content_hash', name='uq_doc_versions_doc_hash'),
    )
    op.create_index('ix_document_versions_document_id', 'document_versions', ['document_id'])
    op.create_index('ix_document_versions_content_hash', 'document_versions', ['content_hash'])
    
    # Add current_version_id to ragdocuments
    op.add_column(
        'ragdocuments',
        sa.Column('current_version_id', postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        'fk_ragdocuments_current_version',
        'ragdocuments', 'document_versions',
        ['current_version_id'], ['id'],
        ondelete='SET NULL'
    )
    op.add_column(
        'ragdocuments',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='Soft delete timestamp')
    )
    
    # =============================================================================
    # jobs - отслеживание Celery задач
    # =============================================================================
    op.create_table(
        'jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('step', sa.String(50), nullable=False, comment='extract|normalize|split|embed.<MODEL>|commit|cleanup'),
        sa.Column('celery_task_id', sa.String(255), nullable=True, unique=True, comment='Celery task UUID'),
        sa.Column('state', sa.String(20), nullable=False, server_default='pending', 
                  comment='pending|running|completed|failed|killed|canceled'),
        sa.Column('retries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_json', postgresql.JSONB(), nullable=True, comment='Error details with taxonomy'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'), 
                  onupdate=sa.text('now()')),
        
        sa.ForeignKeyConstraint(['document_id'], ['ragdocuments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    )
    
    # =============================================================================
    # status_history - история переходов статусов
    # =============================================================================
    op.create_table(
        'status_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('from_status', sa.String(50), nullable=True, comment='Previous status'),
        sa.Column('to_status', sa.String(50), nullable=False, comment='New status'),
        sa.Column('reason', sa.String(255), nullable=True, comment='Reason for transition'),
        sa.Column('actor', sa.String(255), nullable=True, comment='User/system who triggered transition'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        
        sa.ForeignKeyConstraint(['document_id'], ['ragdocuments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_status_history_document_id', 'status_history', ['document_id'])
    op.create_index('ix_status_history_tenant_id', 'status_history', ['tenant_id'])
    op.create_index('ix_status_history_created_at', 'status_history', ['created_at'])
    op.create_index('ix_status_history_to_status', 'status_history', ['to_status'])
    
    # =============================================================================
    # events_outbox - надежная доставка событий через SSE
    # =============================================================================
    op.create_table(
        'events_outbox',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('seq', sa.BigInteger(), nullable=False, unique=True, 
                  comment='Sequential number for ordering (BIGSERIAL equivalent)'),
        sa.Column('type', sa.String(100), nullable=False, 
                  comment='rag.status|rag.embed.progress|rag.tags.updated|rag.deleted'),
        sa.Column('payload_json', postgresql.JSONB(), nullable=False, comment='Event payload'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True, 
                  comment='Timestamp when event was delivered to at least one SSE client'),
    )
    op.create_index('ix_events_outbox_seq', 'events_outbox', ['seq'])
    op.create_index('ix_events_outbox_type', 'events_outbox', ['type'])
    op.create_index('ix_events_outbox_delivered_at', 'events_outbox', ['delivered_at'])
    op.create_index('ix_events_outbox_created_at', 'events_outbox', ['created_at'])
    
    # Create sequence for seq column (since PostgreSQL doesn't have BIGSERIAL in Alembic directly)
    op.execute("""
        CREATE SEQUENCE events_outbox_seq_seq 
        START WITH 1 
        INCREMENT BY 1 
        NO MINVALUE 
        NO MAXVALUE 
        CACHE 1;
    """)
    
    op.execute("""
        ALTER TABLE events_outbox 
        ALTER COLUMN seq 
        SET DEFAULT nextval('events_outbox_seq_seq');
    """)
    
    # =============================================================================
    # model_progress - прогресс эмбеддинга по моделям (альтернатива emb_status)
    # =============================================================================
    # Проверяем, существует ли уже таблица emb_status
    from sqlalchemy import inspect
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = inspector.get_table_names()
    
    if 'emb_status' in existing_tables:
        # Уже есть, просто добавим индексы если нужно
        pass
    else:
        # Создаем как model_progress
        op.create_table(
            'model_progress',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('document_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('model_alias', sa.String(255), nullable=False),
            sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('done', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, 
                      server_default=sa.text('now()'), onupdate=sa.text('now()')),
            
            sa.ForeignKeyConstraint(['document_id'], ['ragdocuments.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('document_id', 'model_alias', name='uq_model_progress_doc_model'),
        )
        op.create_index('ix_model_progress_document_id', 'model_progress', ['document_id'])
        op.create_index('ix_model_progress_model_alias', 'model_progress', ['model_alias'])


def downgrade() -> None:
    # Drop tables in reverse order
    op.execute("DROP SEQUENCE IF EXISTS events_outbox_seq_seq CASCADE")
    
    op.drop_table('model_progress')
    op.drop_table('events_outbox')
    op.drop_table('status_history')
    op.drop_table('jobs')
    
    # Remove columns from ragdocuments
    op.drop_constraint('fk_ragdocuments_current_version', 'ragdocuments', type_='foreignkey')
    op.drop_column('ragdocuments', 'deleted_at')
    op.drop_column('ragdocuments', 'current_version_id')
    
    op.drop_table('document_versions')

