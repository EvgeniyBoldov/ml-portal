"""fix ragdocuments schema: status default, tenant_id FK, remove legacy fields, add missing indexes

Revision ID: 20251114_000000
Revises: 20251113_220000
Create Date: 2025-11-14 00:00:00

"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20251114_000000"
down_revision = "20251113_220000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Fix ragdocuments schema to match model:
    1. Fix status default from 'processed' to 'uploaded'
    2. Add tenant_id FK constraint to tenants
    3. Remove legacy fields: published_at, published_by, current_version_id, deleted_at
    4. Add missing indexes
    """
    
    # 1. Fix status default value
    # First, change default for new rows
    op.alter_column(
        "ragdocuments",
        "status",
        server_default="uploaded",
        existing_type=postgresql.ENUM(
            'uploaded', 'uploading', 'processing', 'processed', 'ready', 'failed', 'archived', 'queued',
            name='documentstatus'
        ),
        existing_nullable=False
    )
    
    # 2. Add tenant_id FK constraint to tenants (if not exists)
    # First check if constraint exists
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    fk_constraints = [fk['name'] for fk in inspector.get_foreign_keys('ragdocuments')]
    
    if 'fk_ragdocuments_tenant_id_tenants' not in fk_constraints:
        op.create_foreign_key(
            constraint_name="fk_ragdocuments_tenant_id_tenants",
            source_table="ragdocuments",
            referent_table="tenants",
            local_cols=["tenant_id"],
            remote_cols=["id"],
            ondelete="CASCADE"
        )
    
    # 3. Remove legacy fields (check if they exist first)
    columns = {col['name'] for col in inspector.get_columns('ragdocuments')}
    
    # Drop FK constraint for current_version_id if exists
    if 'current_version_id' in columns:
        fk_current_version = [fk for fk in inspector.get_foreign_keys('ragdocuments') 
                              if 'current_version' in fk['name']]
        if fk_current_version:
            op.drop_constraint(fk_current_version[0]['name'], "ragdocuments", type_="foreignkey")
        op.drop_column("ragdocuments", "current_version_id")
    
    if 'published_at' in columns:
        op.drop_column("ragdocuments", "published_at")
    
    if 'published_by' in columns:
        op.drop_column("ragdocuments", "published_by")
    
    if 'deleted_at' in columns:
        op.drop_column("ragdocuments", "deleted_at")
    
    # 4. Add missing indexes (check if they exist first)
    indexes = {idx['name'] for idx in inspector.get_indexes('ragdocuments')}
    
    if 'ix_ragdocuments_tenant_id' not in indexes:
        op.create_index("ix_ragdocuments_tenant_id", "ragdocuments", ["tenant_id"])
    
    if 'ix_ragdocuments_uploaded_by' not in indexes:
        op.create_index("ix_ragdocuments_uploaded_by", "ragdocuments", ["uploaded_by"])
    
    if 'ix_ragdocuments_status' not in indexes:
        op.create_index("ix_ragdocuments_status", "ragdocuments", ["status"])
    
    if 'ix_ragdocuments_scope' not in indexes:
        op.create_index("ix_ragdocuments_scope", "ragdocuments", ["scope"])


def downgrade() -> None:
    """Revert changes"""
    
    # Drop indexes
    op.drop_index("ix_ragdocuments_scope", table_name="ragdocuments")
    op.drop_index("ix_ragdocuments_status", table_name="ragdocuments")
    op.drop_index("ix_ragdocuments_uploaded_by", table_name="ragdocuments")
    op.drop_index("ix_ragdocuments_tenant_id", table_name="ragdocuments")
    
    # Add back legacy columns
    op.add_column("ragdocuments", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ragdocuments", sa.Column("published_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ragdocuments", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("ragdocuments", sa.Column("current_version_id", postgresql.UUID(as_uuid=True), nullable=True))
    
    # Drop tenant_id FK
    op.drop_constraint("fk_ragdocuments_tenant_id_tenants", "ragdocuments", type_="foreignkey")
    
    # Revert status default
    op.alter_column(
        "ragdocuments",
        "status",
        server_default="processed",
        existing_type=postgresql.ENUM(
            'uploaded', 'uploading', 'processing', 'processed', 'ready', 'failed', 'archived', 'queued',
            name='documentstatus'
        ),
        existing_nullable=False
    )
