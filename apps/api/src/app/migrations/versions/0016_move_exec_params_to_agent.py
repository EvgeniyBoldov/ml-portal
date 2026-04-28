"""Move execution params from agent_versions to agents.

- agents: add temperature, max_tokens, requires_confirmation_for_write, risk_level
- agent_versions: drop model, temperature, max_tokens, max_steps, max_retries, timeout_s,
                  requires_confirmation_for_write, risk_level

Data migration: copy values from the published version → agent row before dropping columns.

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-27
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add new columns to agents
    op.add_column("agents", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("agents", sa.Column("max_tokens", sa.Integer(), nullable=True))
    op.add_column("agents", sa.Column("requires_confirmation_for_write", sa.Boolean(), nullable=True))
    op.add_column("agents", sa.Column("risk_level", sa.String(20), nullable=True))

    # 2. Migrate data: copy from published version → agent (take first published per agent)
    op.execute("""
        UPDATE agents a
        SET
            temperature                    = av.temperature,
            max_tokens                     = av.max_tokens,
            requires_confirmation_for_write = av.requires_confirmation_for_write,
            risk_level                     = av.risk_level,
            model                          = COALESCE(av.model, a.model)
        FROM agent_versions av
        WHERE av.agent_id = a.id
          AND av.status = 'published'
          AND av.id = (
              SELECT id FROM agent_versions
              WHERE agent_id = a.id AND status = 'published'
              ORDER BY version DESC
              LIMIT 1
          )
    """)

    # 3. Drop moved columns from agent_versions
    op.drop_column("agent_versions", "model")
    op.drop_column("agent_versions", "temperature")
    op.drop_column("agent_versions", "max_tokens")
    op.drop_column("agent_versions", "max_steps")
    op.drop_column("agent_versions", "max_retries")
    op.drop_column("agent_versions", "timeout_s")
    op.drop_column("agent_versions", "requires_confirmation_for_write")
    op.drop_column("agent_versions", "risk_level")


def downgrade() -> None:
    # Restore columns to agent_versions (data is lost — this is intentional)
    op.add_column("agent_versions", sa.Column("model", sa.String(100), nullable=True))
    op.add_column("agent_versions", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("agent_versions", sa.Column("max_tokens", sa.Integer(), nullable=True))
    op.add_column("agent_versions", sa.Column("max_steps", sa.Integer(), nullable=True))
    op.add_column("agent_versions", sa.Column("max_retries", sa.Integer(), nullable=True))
    op.add_column("agent_versions", sa.Column("timeout_s", sa.Integer(), nullable=True))
    op.add_column("agent_versions", sa.Column("requires_confirmation_for_write", sa.Boolean(), nullable=True))
    op.add_column("agent_versions", sa.Column("risk_level", sa.String(20), nullable=True))

    # Remove added columns from agents
    op.drop_column("agents", "temperature")
    op.drop_column("agents", "max_tokens")
    op.drop_column("agents", "requires_confirmation_for_write")
    op.drop_column("agents", "risk_level")
