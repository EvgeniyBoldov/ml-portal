"""Normalize persisted chat turn lifecycle values.

Revision ID: 0206
Revises: 0205
"""
from alembic import op
import sqlalchemy as sa

revision = "0206"
down_revision = "0205"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_turns",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(sa.text("UPDATE chat_turns SET heartbeat_at = started_at WHERE heartbeat_at IS NULL"))
    op.alter_column(
        "chat_turns", "heartbeat_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )
    op.execute(sa.text("UPDATE chat_turns SET status = 'running' WHERE status IN ('started', 'resumed')"))
    op.execute(sa.text("""
        UPDATE chat_turns
        SET status = CASE
            WHEN pause_status = 'waiting_confirmation' THEN 'waiting_confirmation'
            ELSE 'waiting_input'
        END
        WHERE status = 'paused'
    """))
    op.alter_column(
        "chat_turns", "status",
        existing_type=sa.String(length=50),
        server_default="running",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE chat_turns SET status = 'started' WHERE status = 'running'"))
    op.execute(sa.text("""
        UPDATE chat_turns
        SET status = 'paused'
        WHERE status IN ('waiting_input', 'waiting_confirmation')
    """))
    op.alter_column(
        "chat_turns", "status",
        existing_type=sa.String(length=50),
        server_default="started",
        existing_nullable=False,
    )
    op.drop_column("chat_turns", "heartbeat_at")
