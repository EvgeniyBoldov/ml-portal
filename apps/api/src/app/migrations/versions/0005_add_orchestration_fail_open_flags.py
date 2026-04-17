"""Add fail-open runtime flags to orchestration settings

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orchestration_settings",
        sa.Column("triage_fail_open", sa.Boolean(), nullable=True, server_default=sa.true()),
    )
    op.add_column(
        "orchestration_settings",
        sa.Column("preflight_fail_open", sa.Boolean(), nullable=True, server_default=sa.false()),
    )
    op.add_column(
        "orchestration_settings",
        sa.Column("planner_fail_open", sa.Boolean(), nullable=True, server_default=sa.false()),
    )
    op.add_column(
        "orchestration_settings",
        sa.Column("preflight_fail_open_message", sa.Text(), nullable=True),
    )
    op.add_column(
        "orchestration_settings",
        sa.Column("planner_fail_open_message", sa.Text(), nullable=True),
    )

    op.execute(
        sa.text(
            """
            UPDATE orchestration_settings
            SET
                triage_fail_open = COALESCE(triage_fail_open, true),
                preflight_fail_open = COALESCE(preflight_fail_open, false),
                planner_fail_open = COALESCE(planner_fail_open, false)
            """
        )
    )

    op.alter_column("orchestration_settings", "triage_fail_open", server_default=None)
    op.alter_column("orchestration_settings", "preflight_fail_open", server_default=None)
    op.alter_column("orchestration_settings", "planner_fail_open", server_default=None)


def downgrade() -> None:
    op.drop_column("orchestration_settings", "planner_fail_open_message")
    op.drop_column("orchestration_settings", "preflight_fail_open_message")
    op.drop_column("orchestration_settings", "planner_fail_open")
    op.drop_column("orchestration_settings", "preflight_fail_open")
    op.drop_column("orchestration_settings", "triage_fail_open")
