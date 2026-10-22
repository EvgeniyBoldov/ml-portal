"""Persist refresh-token rotation and revocation state.

Revision ID: 0199
Revises: 0198
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0199"
down_revision = "0198"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_refresh_sessions",
        sa.Column("jti", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_auth_refresh_sessions_family_id", "auth_refresh_sessions", ["family_id"])
    op.create_index("ix_auth_refresh_sessions_user_id", "auth_refresh_sessions", ["user_id"])
    op.create_index("ix_auth_refresh_sessions_expires_at", "auth_refresh_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_auth_refresh_sessions_expires_at", table_name="auth_refresh_sessions")
    op.drop_index("ix_auth_refresh_sessions_user_id", table_name="auth_refresh_sessions")
    op.drop_index("ix_auth_refresh_sessions_family_id", table_name="auth_refresh_sessions")
    op.drop_table("auth_refresh_sessions")
