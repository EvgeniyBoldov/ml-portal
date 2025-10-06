"""Add RBAC scope functionality

Revision ID: 20250103_150000
Revises: 20250102_120000_add_user_tenants_m2m
Create Date: 2025-01-03 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250103_150000'
down_revision = '20250102_120000'
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade to add RBAC scope functionality:
    1. Add scope field to rag_documents  
    2. Add tenant_id to rag_documents
    3. Add user permission flags
    4. Update audit_logs with scope tracking
    5. Add versioning fields for global documents
    """
    
    # =============================================================================
    # CREATE ENUMS
    # =============================================================================
    
    # Create DocumentScope enum
    scope_enum = postgresql.ENUM('local', 'global', name='documentscope')
    scope_enum.create(op.get_bind())
    
    # Create DocumentStatus enum  
    status_enum = postgresql.ENUM('uploading', 'processing', 'processed', 'failed', 'archived', name='documentstatus')
    status_enum.create(op.get_bind())
    
    # =============================================================================
    # UPDATE RAG_DOCUMENTS TABLE
    # =============================================================================
    
    # Add scope column with default 'local'
    op.add_column('ragdocuments', 
        sa.Column('scope', scope_enum, nullable=False, server_default='local'))
    
    # Add tenant_id column (nullable for global docs)
    op.add_column('ragdocuments', 
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    
    # Add versioning fields for global documents
    op.add_column('ragdocuments',
        sa.Column('global_version', sa.Integer(), nullable=True))
    
    op.add_column('ragdocuments',
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True))
        
    op.add_column('ragdocuments',
        sa.Column('published_by', postgresql.UUID(as_uuid=True), nullable=True))
    
    # Update status column to use new enum type
    op.alter_column('ragdocuments', 'status',
        type_=status_enum,
        postgresql_using='status::documentstatus')
    
    # =============================================================================
    # UPDATE RAG_CHUNKS TABLE
    # =============================================================================
    
    # Add scope column to chunks (inherited from document)
    op.add_column('rag_chunks', 
        sa.Column('scope', scope_enum, nullable=False, server_default='local'))
    
    # Add tenant_id column to chunks
    op.add_column('rag_chunks', 
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    
    # =============================================================================
    # UPDATE USERS TABLE
    # =============================================================================
    
    # Add user permission flags
    op.add_column('users', 
        sa.Column('can_edit_local_docs', sa.Boolean(), nullable=False, server_default='false'))
    
    op.add_column('users', 
        sa.Column('can_edit_global_docs', sa.Boolean(), nullable=False, server_default='false'))
    
    op.add_column('users', 
        sa.Column('can_trigger_reindex', sa.Boolean(), nullable=False, server_default='false'))
    
    op.add_column('users', 
        sa.Column('can_manage_users', sa.Boolean(), nullable=False, server_default='false'))
    
    # =============================================================================
    # UPDATE AUDIT_LOGS TABLE
    # =============================================================================
    
    # Add tenant_id and scope_snapshot to audit logs
    op.add_column('audit_logs', 
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    
    op.add_column('audit_logs', 
        sa.Column('scope_snapshot', sa.String(20), nullable=True))
    
    # =============================================================================
    # CREATE INDEXES
    # =============================================================================
    
    # RAG Documents indexes
    op.create_index('idx_rag_documents_tenant_scope', 'ragdocuments', ['tenant_id', 'scope'])
    op.create_index('idx_rag_documents_scope_status', 'ragdocuments', ['scope', 'status'])
    op.create_index('idx_rag_documents_global_version', 'ragdocuments', ['global_version'])
    op.create_index('idx_rag_documents_scope_tenant_lookup', 'ragdocuments', ['scope', 'tenant_id'])
    
    # RAG Chunks indexes
    op.create_index('idx_rag_chunks_tenant_scope', 'rag_chunks', ['tenant_id', 'scope'])
    
    # Audit logs indexes
    op.create_index('idx_audit_logs_tenant_id', 'audit_logs', ['tenant_id'])
    op.create_index('idx_audit_logs_object_type', 'audit_logs', ['object_type'])
    op.create_index('idx_audit_logs_action', 'audit_logs', ['action'])
    op.create_index('idx_audit_logs_created_at', 'audit_logs', ['created_at'])
    op.create_index('idx_audit_logs_object_lookup', 'audit_logs', ['object_type', 'object_id'])
    
    # =============================================================================
    # UPDATE CONSTRAINT FOR USER_PERMISSIONS VALIDATION
    # =============================================================================
    
    # Create check constraint for user permissions (only editor/admin can have permission flags)
    op.execute("""
        ALTER TABLE users ADD CONSTRAINT chk_user_permissions_role 
        CHECK (
            (role IN ('reader') AND 
             can_edit_local_docs = false AND 
             can_edit_global_docs = false AND 
             can_trigger_reindex = false AND 
             can_manage_users = false)
            OR
            (role IN ('editor', 'admin'))
        )
    """)


def downgrade():
    """
    Downgrade RBAC scope functionality:
    1. Remove constraints and indexes
    2. Drop columns
    3. Drop enums
    """
    
    # =============================================================================
    # DROP CONSTRAINTS AND INDEXES
    # =============================================================================
    
    # Drop constraint
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS chk_user_permissions_role")
    
    # Drop indexes
    op.drop_index('idx_rag_documents_tenant_scope')
    op.drop_index('idx_rag_documents_scope_status')
    op.drop_index('idx_rag_documents_global_version')
    op.drop_index('idx_rag_documents_scope_tenant_lookup')
    
    op.drop_index('idx_rag_chunks_tenant_scope')
    
    op.drop_index('idx_audit_logs_tenant_id')
    op.drop_index('idx_audit_logs_object_type')
    op.drop_index('idx_audit_logs_action')
    op.drop_index('idx_audit_logs_created_at')
    op.drop_index('idx_audit_logs_object_lookup')
    
    # =============================================================================
    # DROP COLUMNS
    # =============================================================================
    
    # Drop RAG Documents columns
    op.drop_column('ragdocuments', 'published_by')
    op.drop_column('ragdocuments', 'published_at')
    op.drop_column('ragdocuments', 'global_version')
    op.drop_column('ragdocuments', 'tenant_id')
    op.drop_column('ragdocuments', 'scope')
    
    # Drop RAG Chunks columns
    op.drop_column('rag_chunks', 'tenant_id')
    op.drop_column('rag_chunks', 'scope')
    
    # Drop Users columns
    op.drop_column('users', 'can_manage_users')
    op.drop_column('users', 'can_trigger_reindex')
    op.drop_column('users', 'can_edit_global_docs')
    op.drop_column('users', 'can_edit_local_docs')
    
    # Drop Audit logs columns
    op.drop_column('audit_logs', 'scope_snapshot')
    op.drop_column('audit_logs', 'tenant_id')
    
    # =============================================================================
    # DROP ENUMS
    # =============================================================================
    
    op.execute("DROP TYPE IF EXISTS documentstatus")
    op.execute("DROP TYPE IF EXISTS documentscope")
