"""add agent routing fields

Revision ID: 0068
Revises: 0067
Create Date: 2026-02-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0068"
down_revision: Union[str, Sequence[str], None] = "0067"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("tag", sa.String(length=100), nullable=True))
    op.add_column("agents", sa.Column("category", sa.String(length=100), nullable=True))
    op.add_column("agents", sa.Column("routing_example", sa.Text(), nullable=True))

    op.add_column("agents", sa.Column("is_routable", sa.Boolean(), nullable=True))
    op.execute("UPDATE agents SET is_routable = false WHERE is_routable IS NULL")
    op.alter_column("agents", "is_routable", nullable=False, server_default=sa.text("false"))


def downgrade() -> None:
    op.drop_column("agents", "is_routable")
    op.drop_column("agents", "routing_example")
    op.drop_column("agents", "category")
    op.drop_column("agents", "tag")
