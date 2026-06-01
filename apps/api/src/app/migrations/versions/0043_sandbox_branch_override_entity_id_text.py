"""Change sandbox branch override entity_id to text

Revision ID: 0043
Revises: 0042
Create Date: 2026-06-01

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "sandbox_branch_overrides",
        "entity_id",
        existing_type=sa.UUID(),
        type_=sa.String(length=255),
        existing_nullable=True,
        postgresql_using="entity_id::text",
    )


def downgrade():
    op.alter_column(
        "sandbox_branch_overrides",
        "entity_id",
        existing_type=sa.String(length=255),
        type_=sa.UUID(),
        existing_nullable=True,
        postgresql_using="NULLIF(entity_id, '')::uuid",
    )

