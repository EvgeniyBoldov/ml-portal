"""Separate platform admin from tenant administrator/editor roles.

Revision ID: 0201
Revises: 0200
"""
from alembic import op
import sqlalchemy as sa

revision = "0201"
down_revision = "0200"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user_tenants", sa.Column("is_tenant_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user_tenants", sa.Column("is_data_editor", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(sa.text("UPDATE users SET is_admin = (role = 'admin')"))
    op.execute(sa.text("""
        UPDATE user_tenants ut SET is_data_editor = true
        FROM users u WHERE u.id = ut.user_id AND u.role = 'editor'
    """))


def downgrade() -> None:
    op.drop_column("user_tenants", "is_data_editor")
    op.drop_column("user_tenants", "is_tenant_admin")
    op.drop_column("users", "is_admin")
