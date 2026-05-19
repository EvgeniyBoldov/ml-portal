"""Detach execution_memories from tenant and enforce nullable facts.tenant_id.

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-18
"""
from __future__ import annotations

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_execution_memories_tenant_id")
    op.execute("ALTER TABLE execution_memories DROP COLUMN IF EXISTS tenant_id CASCADE")

    # memory tenant scope stays optional by design
    op.execute("ALTER TABLE facts ALTER COLUMN tenant_id DROP NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE execution_memories ADD COLUMN IF NOT EXISTS tenant_id UUID")
    op.execute("CREATE INDEX IF NOT EXISTS ix_execution_memories_tenant_id ON execution_memories (tenant_id)")
