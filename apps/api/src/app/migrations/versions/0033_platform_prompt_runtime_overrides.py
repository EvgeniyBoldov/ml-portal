"""Add platform prompt/runtime override fields.

Revision ID: 0033_plat_prompt_ovr
Revises: 0032_periodic_tasks_registry
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0033_plat_prompt_ovr"
down_revision = "0032_periodic_tasks_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_settings",
        sa.Column("required_operation_retry_instruction", sa.Text(), nullable=True),
    )
    op.add_column(
        "platform_settings",
        sa.Column("operations_rules_text", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("platform_settings", "operations_rules_text")
    op.drop_column("platform_settings", "required_operation_retry_instruction")
