"""add user_tokens & user_refresh_tokens (idempotent indexes)

Revision ID: 20250908_154500_add_tokens
Revises: 20250904_213024
Create Date: 2025-09-08 15:45:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20250908_154500_add_tokens'
down_revision = '20250904_213024'
branch_labels = None
depends_on = None

def _has_index(inspector: sa.engine.reflection.Inspector, table: str, name: str) -> bool:
    try:
        return any(ix.get("name") == name for ix in inspector.get_indexes(table))
    except Exception:
        return False

def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # user_tokens
    if not insp.has_table("user_tokens"):
        op.create_table(
            "user_tokens",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("token_hash", sa.Text(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if not _has_index(insp, "user_tokens", "ix_user_tokens_user_id"):
        op.create_index("ix_user_tokens_user_id", "user_tokens", ["user_id"])

    # user_refresh_tokens
    if not insp.has_table("user_refresh_tokens"):
        op.create_table(
            "user_refresh_tokens",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("refresh_hash", sa.Text(), nullable=False),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("rotating", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("meta", sa.Text(), nullable=True),
            sa.UniqueConstraint("refresh_hash", name="uq_user_refresh_tokens_refresh_hash"),
        )
    if not _has_index(insp, "user_refresh_tokens", "ix_user_refresh_tokens_user_id"):
        op.create_index("ix_user_refresh_tokens_user_id", "user_refresh_tokens", ["user_id"])

def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # drop indexes first if exist
    if _has_index(insp, "user_refresh_tokens", "ix_user_refresh_tokens_user_id"):
        op.drop_index("ix_user_refresh_tokens_user_id", table_name="user_refresh_tokens")
    if _has_index(insp, "user_tokens", "ix_user_tokens_user_id"):
        op.drop_index("ix_user_tokens_user_id", table_name="user_tokens")

    if insp.has_table("user_refresh_tokens"):
        op.drop_table("user_refresh_tokens")
    if insp.has_table("user_tokens"):
        op.drop_table("user_tokens")
