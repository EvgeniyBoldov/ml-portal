"""Add v3 runtime memory columns to execution_memories

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-18

Adds columns used by the new WorkingMemory model (runtime v3):
  - intent               VARCHAR(20)   — triage intent (final/clarify/orchestrate/resume)
  - used_tool_calls      INTEGER       — operation calls consumed in this run
  - used_wall_time_ms    INTEGER       — wall-time budget consumption
  - recent_messages      JSONB         — cross-turn context snapshot

Non-destructive. Table name (`execution_memories`) is preserved.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "execution_memories",
        sa.Column("intent", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "execution_memories",
        sa.Column(
            "used_tool_calls",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "execution_memories",
        sa.Column(
            "used_wall_time_ms",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "execution_memories",
        sa.Column(
            "recent_messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    # Drop server_defaults once columns exist — defaults are handled by Python.
    op.alter_column("execution_memories", "used_tool_calls", server_default=None)
    op.alter_column("execution_memories", "used_wall_time_ms", server_default=None)
    op.alter_column("execution_memories", "recent_messages", server_default=None)


def downgrade() -> None:
    op.drop_column("execution_memories", "recent_messages")
    op.drop_column("execution_memories", "used_wall_time_ms")
    op.drop_column("execution_memories", "used_tool_calls")
    op.drop_column("execution_memories", "intent")
