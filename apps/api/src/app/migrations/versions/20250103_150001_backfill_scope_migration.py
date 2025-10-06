"""Backfill existing documents with scope migration

Revision ID: 20250103_150001
Revises: 20250103_150000
Create Date: 2025-01-03 15:00:01.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250103_150001'
down_revision = '20250103_150000'
branch_labels = None
depends_on = None


def upgrade():
    """
    Backfill existing documents:
    1. Set all existing documents to 'local' scope
    2. Set tenant_id from user's default tenant
    3. Update chunk metadata in Qdrant
    """
    
    connection = op.get_bind()
    
    # =============================================================================
    # CALCULATE TENANT_ID FROM USER DEFAULT TENANTS
    # =============================================================================
    
    # Update rag_documents with tenant_id from user's default tenant
    connection.execute("""
        UPDATE rag_documents 
        SET tenant_id = ut.tenant_id
        FROM user_tenants ut
        WHERE rag_documents.user_id = ut.user_id 
        AND ut.is_default = true
        AND rag_documents.tenant_id IS NULL
    """)
    
    # Update rag_chunks to inherit scope and tenant_id from documents
    connection.execute("""
        UPDATE rag_chunks 
        SET 
            scope = rd.scope,
            tenant_id = rd.tenant_id
        FROM rag_documents rd
        WHERE rag_chunks.document_id = rd.id
    """)


def downgrade():
    """
    This migration is irreversible - backfill operations cannot be undone
    """
    pass
