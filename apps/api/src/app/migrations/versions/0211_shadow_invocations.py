"""Persist asynchronous shadow invocations.

Revision ID: 0211
Revises: 0210
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0211"
down_revision = "0210"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shadow_invocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent", sa.String(255), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("scopes", postgresql.JSONB(), nullable=False),
        sa.Column("request_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error", sa.String(255)),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True)),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_shadow_invocations_user_id", "shadow_invocations", ["user_id"])
    op.create_index("ix_shadow_invocations_pending", "shadow_invocations", ["status", "updated_at"])


def downgrade() -> None:
    op.drop_table("shadow_invocations")
