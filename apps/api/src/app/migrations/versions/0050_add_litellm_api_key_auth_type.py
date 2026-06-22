"""add litellm api key auth type

Revision ID: 0050_add_litellm_api_key_auth_type
Revises: 0049_remove_planner_direct_answer_and_add_agent_allow_all_collections
Create Date: 2026-06-22 08:15:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0050_add_litellm_api_key_auth_type"
down_revision = "0049_remove_planner_direct_answer_and_add_agent_allow_all_collections"
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
