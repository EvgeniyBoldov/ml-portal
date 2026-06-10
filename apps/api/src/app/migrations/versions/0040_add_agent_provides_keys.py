"""Add provides_keys to agents table.

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-11 00:20:00
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column(
            "provides_keys",
            sa.ARRAY(sa.String()),
            nullable=True,
            comment="Machine-readable keys this agent can resolve (e.g. ['lun_uuid', 'vlan_id']). Used by planner to route agent needs.",
        ),
    )


def downgrade() -> None:
    op.drop_column("agents", "provides_keys")
