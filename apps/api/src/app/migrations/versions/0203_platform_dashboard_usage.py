"""Persist compact production usage independently of runtime journal retention.

Revision ID: 0203
Revises: 0202
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0203"
down_revision = "0202"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_usage",
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("entity_id", sa.String(255), primary_key=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("agent_slug", sa.String(255)),
        sa.Column("model_alias", sa.String(100)),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("error_code", sa.String(120)),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("tokens_in", sa.BigInteger),
        sa.Column("tokens_out", sa.BigInteger),
        sa.Column("token_source", sa.String(16)),
    )
    op.create_index("ix_platform_usage_period", "platform_usage", ["kind", "origin", "started_at"])
    op.create_index("ix_platform_usage_run_id", "platform_usage", ["run_id"])
    op.create_table("platform_usage_coverage",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.execute("INSERT INTO platform_usage_coverage (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("platform_usage_coverage")
    op.drop_table("platform_usage")
