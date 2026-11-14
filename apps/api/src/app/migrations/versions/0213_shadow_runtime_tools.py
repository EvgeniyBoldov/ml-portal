"""Enable memory scope selection and durable standalone operation admission.

Revision ID: 0213
Revises: 0212
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0213"
down_revision = "0212"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shadow_invocations", sa.Column("scope_keys", postgresql.JSONB(), nullable=True))
    op.create_table(
        "shadow_execution_guards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("calls", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("shadow_execution_guards")
    op.drop_column("shadow_invocations", "scope_keys")
