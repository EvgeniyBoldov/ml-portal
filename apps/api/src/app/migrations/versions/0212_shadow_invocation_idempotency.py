"""Add owner and tenant scoped async shadow idempotency.

Revision ID: 0212
Revises: 0211
"""
from alembic import op
import sqlalchemy as sa


revision = "0212"
down_revision = "0211"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shadow_invocations", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.add_column("shadow_invocations", sa.Column("request_fingerprint", sa.String(length=64), nullable=True))
    op.create_unique_constraint(
        "uq_shadow_invocations_user_tenant_idempotency",
        "shadow_invocations",
        ["user_id", "tenant_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_shadow_invocations_user_tenant_idempotency", "shadow_invocations", type_="unique")
    op.drop_column("shadow_invocations", "request_fingerprint")
    op.drop_column("shadow_invocations", "idempotency_key")
