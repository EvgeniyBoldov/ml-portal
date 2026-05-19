"""Detach chat entities from tenant ownership.

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-18
"""
from __future__ import annotations

from alembic import op


revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chats_tenant_id")
    op.execute("DROP INDEX IF EXISTS ix_chats_tenant_created")
    op.execute("DROP INDEX IF EXISTS ix_chats_tenant_owner")
    op.execute("DROP INDEX IF EXISTS ix_chats_tenant_name")
    op.execute("DROP INDEX IF EXISTS ix_chatmessages_tenant_id")
    op.execute("DROP INDEX IF EXISTS ix_chatmessages_tenant_created")
    op.execute("DROP INDEX IF EXISTS ix_chatmessages_tenant_chat")
    op.execute("DROP INDEX IF EXISTS ix_chat_turns_tenant_id")
    op.execute("DROP INDEX IF EXISTS ix_chat_attachments_tenant_id")
    op.execute("DROP INDEX IF EXISTS ix_chat_summaries_tenant_id")

    op.execute("ALTER TABLE chat_summaries DROP COLUMN IF EXISTS tenant_id CASCADE")
    op.execute("ALTER TABLE chat_attachments DROP COLUMN IF EXISTS tenant_id CASCADE")
    op.execute("ALTER TABLE chat_turns DROP COLUMN IF EXISTS tenant_id CASCADE")
    op.execute("ALTER TABLE chatmessages DROP COLUMN IF EXISTS tenant_id CASCADE")
    op.execute("ALTER TABLE chats DROP COLUMN IF EXISTS tenant_id CASCADE")

    op.execute("CREATE INDEX IF NOT EXISTS ix_chats_owner_created ON chats (owner_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chats_owner_name ON chats (owner_id, name)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chatmessages_chat_created ON chatmessages (chat_id, created_at)")


def downgrade() -> None:
    op.execute("ALTER TABLE chats ADD COLUMN IF NOT EXISTS tenant_id UUID")
    op.execute("ALTER TABLE chatmessages ADD COLUMN IF NOT EXISTS tenant_id UUID")
    op.execute("ALTER TABLE chat_turns ADD COLUMN IF NOT EXISTS tenant_id UUID")
    op.execute("ALTER TABLE chat_attachments ADD COLUMN IF NOT EXISTS tenant_id UUID")
    op.execute("ALTER TABLE chat_summaries ADD COLUMN IF NOT EXISTS tenant_id UUID")

    op.execute("DROP INDEX IF EXISTS ix_chats_owner_created")
    op.execute("DROP INDEX IF EXISTS ix_chats_owner_name")
    op.execute("DROP INDEX IF EXISTS ix_chatmessages_chat_created")

    op.execute("CREATE INDEX IF NOT EXISTS ix_chats_tenant_id ON chats (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chats_tenant_created ON chats (tenant_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chats_tenant_owner ON chats (tenant_id, owner_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chats_tenant_name ON chats (tenant_id, name)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chatmessages_tenant_id ON chatmessages (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chatmessages_tenant_created ON chatmessages (tenant_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chatmessages_tenant_chat ON chatmessages (tenant_id, chat_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_turns_tenant_id ON chat_turns (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_chat_attachments_tenant_id ON chat_attachments (tenant_id)")
