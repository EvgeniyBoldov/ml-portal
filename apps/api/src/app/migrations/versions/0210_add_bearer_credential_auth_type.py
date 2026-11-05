"""add bearer credential auth type

Revision ID: 0210
Revises: 0209
"""
from alembic import op


revision = "0210"
down_revision = "0209"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_credential_auth_type", "credentials", type_="check")
    op.create_check_constraint(
        "ck_credential_auth_type",
        "credentials",
        "auth_type IN ('token', 'bearer', 'basic', 'oauth', 'api_key', 'litellm_api_key')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_credential_auth_type", "credentials", type_="check")
    op.create_check_constraint(
        "ck_credential_auth_type",
        "credentials",
        "auth_type IN ('token', 'basic', 'oauth', 'api_key', 'litellm_api_key')",
    )
