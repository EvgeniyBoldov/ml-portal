"""Drop legacy platform cap columns in platform_settings.

Revision ID: 0031_drop_platform_caps_columns
Revises: 0030
Create Date: 2026-05-22
"""
import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision = "0031_drop_platform_caps_columns"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("platform_settings", "abs_max_plan_steps")
    op.drop_column("platform_settings", "abs_max_concurrency")
    op.drop_column("platform_settings", "abs_max_task_runtime_s")
    op.drop_column("platform_settings", "abs_max_tool_calls_per_step")


def downgrade() -> None:
    op.add_column("platform_settings", sa.Column("abs_max_tool_calls_per_step", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("abs_max_task_runtime_s", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("abs_max_concurrency", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("abs_max_plan_steps", sa.Integer(), nullable=True))
