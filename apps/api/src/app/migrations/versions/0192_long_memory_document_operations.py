"""Durable LongMemory add/delete operations and document generation fence.

Revision ID: 0192
Revises: 0191
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0192"
down_revision = "0191"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ragdocuments", sa.Column("long_memory_generation", sa.Integer(), nullable=False, server_default="0"))
    op.create_table("long_memory_document_operations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("document_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("progress", JSONB, nullable=False, server_default="{}"),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("ix_long_memory_document_ops_document", "long_memory_document_operations", ["document_id"])
    op.create_index("ix_long_memory_document_ops_status", "long_memory_document_operations", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_table("long_memory_document_operations")
    op.drop_column("ragdocuments", "long_memory_generation")
