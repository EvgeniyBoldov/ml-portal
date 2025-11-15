"""Cleanup legacy status systems (revision: 0016_cleanup_status)

Remove:
- Source.status field (use RAGDocument.status instead)
- state_engine tables (Job, StatusHistory, DocumentVersion, ModelProgress)

Keep:
- RAGDocument.status (main status)
- RAGStatus (detailed node statuses for SSE)
- EventOutbox (used for SSE)
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic. Do not exceed 32 chars per Alembic rules.
revision = "0016_cleanup_status"
down_revision = "0015_add_additional_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop Source.status constraint and column
    op.drop_constraint('ck_sources_status', 'sources', type_='check')
    op.drop_index('ix_sources_status', table_name='sources')
    op.drop_column('sources', 'status')
    
    # 2. Drop state_engine tables (not used in production)
    # Drop in reverse order of dependencies
    
    # model_progress
    op.drop_index("ix_model_progress_model_alias", table_name="model_progress")
    op.drop_index("ix_model_progress_document_id", table_name="model_progress")
    op.drop_table("model_progress")
    
    # status_history
    op.drop_index("ix_status_history_to_status", table_name="status_history")
    op.drop_index("ix_status_history_created_at", table_name="status_history")
    op.drop_index("ix_status_history_tenant_id", table_name="status_history")
    op.drop_index("ix_status_history_document_id", table_name="status_history")
    op.drop_table("status_history")
    
    # jobs
    op.drop_index("ix_jobs_updated_at", table_name="jobs")
    op.drop_index("ix_jobs_step", table_name="jobs")
    op.drop_index("ix_jobs_state", table_name="jobs")
    op.drop_index("ix_jobs_celery_task_id", table_name="jobs")
    op.drop_index("ix_jobs_tenant_id", table_name="jobs")
    op.drop_index("ix_jobs_document_id", table_name="jobs")
    op.drop_table("jobs")
    
    # document_versions
    op.drop_index("ix_document_versions_content_hash", table_name="document_versions")
    op.drop_index("ix_document_versions_document_id", table_name="document_versions")
    op.drop_table("document_versions")


def downgrade() -> None:
    # Recreate document_versions
    op.create_table(
        "document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["document_id"], ["ragdocuments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "content_hash", name="uq_doc_versions_doc_hash"),
    )
    op.create_index("ix_document_versions_document_id", "document_versions", ["document_id"])
    op.create_index("ix_document_versions_content_hash", "document_versions", ["content_hash"])
    
    # Recreate jobs
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step", sa.String(length=50), nullable=False),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True, unique=True),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_json", postgresql.JSONB, nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["document_id"], ["ragdocuments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_jobs_document_id", "jobs", ["document_id"])
    op.create_index("ix_jobs_tenant_id", "jobs", ["tenant_id"])
    op.create_index("ix_jobs_celery_task_id", "jobs", ["celery_task_id"])
    op.create_index("ix_jobs_state", "jobs", ["state"])
    op.create_index("ix_jobs_step", "jobs", ["step"])
    op.create_index("ix_jobs_updated_at", "jobs", ["updated_at"])
    
    # Recreate status_history
    op.create_table(
        "status_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("from_status", sa.String(length=50), nullable=True),
        sa.Column("to_status", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("actor", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["document_id"], ["ragdocuments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_status_history_document_id", "status_history", ["document_id"])
    op.create_index("ix_status_history_tenant_id", "status_history", ["tenant_id"])
    op.create_index("ix_status_history_created_at", "status_history", ["created_at"])
    op.create_index("ix_status_history_to_status", "status_history", ["to_status"])
    
    # Recreate model_progress
    op.create_table(
        "model_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_alias", sa.String(length=255), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["document_id"], ["ragdocuments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("document_id", "model_alias", name="uq_model_progress_doc_model"),
    )
    op.create_index("ix_model_progress_document_id", "model_progress", ["document_id"])
    op.create_index("ix_model_progress_model_alias", "model_progress", ["model_alias"])
    
    # Recreate Source.status
    op.add_column('sources', sa.Column('status', sa.String(), nullable=True))
    op.execute("UPDATE sources SET status = 'uploaded' WHERE status IS NULL")
    op.alter_column('sources', 'status', nullable=False)
    op.create_check_constraint(
        'ck_sources_status',
        'sources',
        "status IN ('uploaded','normalized','chunked','embedding','ready','failed','reindexing')"
    )
    op.create_index('ix_sources_status', 'sources', ['status'])
