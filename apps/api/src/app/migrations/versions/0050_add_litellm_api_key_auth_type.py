"""add litellm api key auth type

Revision ID: 0050
Revises: 0049
Create Date: 2026-06-22 08:15:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_credential_auth_type", "credentials", type_="check")
    op.create_check_constraint(
        "ck_credential_auth_type",
        "credentials",
        "auth_type IN ('token', 'basic', 'oauth', 'api_key', 'litellm_api_key')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_credential_auth_type", "credentials", type_="check")
    op.create_check_constraint(
        "ck_credential_auth_type",
        "credentials",
        "auth_type IN ('token', 'basic', 'oauth', 'api_key')",
    )
