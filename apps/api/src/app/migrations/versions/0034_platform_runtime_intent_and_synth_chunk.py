"""Add platform intent templates and synth chunk size.

Revision ID: 0034_plat_runtime_ovr
Revises: 0033_plat_prompt_ovr
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0034_plat_runtime_ovr"
down_revision = "0033_plat_prompt_ovr"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "platform_settings",
        sa.Column("intent_messages", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "platform_settings",
        sa.Column("synth_chunk_size", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("platform_settings", "synth_chunk_size")
    op.drop_column("platform_settings", "intent_messages")
