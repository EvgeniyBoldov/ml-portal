"""Add explicit document_collection_memberships table and backfill from Source.meta.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_collection_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_row_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.source_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "collection_id", name="uq_doc_collection_membership"),
    )
    op.create_index(
        "ix_doc_coll_memberships_tenant",
        "document_collection_memberships",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_doc_coll_memberships_collection",
        "document_collection_memberships",
        ["collection_id"],
        unique=False,
    )
    op.create_index(
        "ix_doc_coll_memberships_source",
        "document_collection_memberships",
        ["source_id"],
        unique=False,
    )

    # Backfill from legacy Source.meta fields. Keep row_id only when UUID-like.
    op.execute(
        """
        INSERT INTO document_collection_memberships
            (id, tenant_id, source_id, collection_id, collection_row_id, created_at, updated_at)
        SELECT
            (
                substr(md5(s.source_id::text || ':' || COALESCE(s.meta #>> '{collection,id}', s.meta ->> 'collection_id')), 1, 8)
                || '-' ||
                substr(md5(s.source_id::text || ':' || COALESCE(s.meta #>> '{collection,id}', s.meta ->> 'collection_id')), 9, 4)
                || '-' ||
                substr(md5(s.source_id::text || ':' || COALESCE(s.meta #>> '{collection,id}', s.meta ->> 'collection_id')), 13, 4)
                || '-' ||
                substr(md5(s.source_id::text || ':' || COALESCE(s.meta #>> '{collection,id}', s.meta ->> 'collection_id')), 17, 4)
                || '-' ||
                substr(md5(s.source_id::text || ':' || COALESCE(s.meta #>> '{collection,id}', s.meta ->> 'collection_id')), 21, 12)
            )::uuid,
            s.tenant_id,
            s.source_id,
            (COALESCE(s.meta #>> '{collection,id}', s.meta ->> 'collection_id'))::uuid,
            CASE
                WHEN COALESCE(s.meta #>> '{collection,row_id}', s.meta ->> 'collection_row_id')
                     ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
                THEN (COALESCE(s.meta #>> '{collection,row_id}', s.meta ->> 'collection_row_id'))::uuid
                ELSE NULL
            END,
            now(),
            now()
        FROM sources s
        WHERE COALESCE(s.meta #>> '{collection,id}', s.meta ->> 'collection_id') IS NOT NULL
        ON CONFLICT ON CONSTRAINT uq_doc_collection_membership DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_doc_coll_memberships_source", table_name="document_collection_memberships")
    op.drop_index("ix_doc_coll_memberships_collection", table_name="document_collection_memberships")
    op.drop_index("ix_doc_coll_memberships_tenant", table_name="document_collection_memberships")
    op.drop_table("document_collection_memberships")
