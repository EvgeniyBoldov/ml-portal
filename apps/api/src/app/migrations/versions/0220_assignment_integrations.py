"""Manage assignment integrations and their inbound tokens."""

import sqlalchemy as sa
from alembic import op

revision = "0220"
down_revision = "0219"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assignment_integrations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source", sa.String(97), nullable=False, unique=True),
        sa.Column("connector_id", sa.Uuid(), sa.ForeignKey("tool_instances.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_assignment_integrations_connector_id", "assignment_integrations", ["connector_id"])
    op.create_table(
        "assignment_integration_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("integration_id", sa.Uuid(), sa.ForeignKey("assignment_integrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("token_prefix", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_assignment_integration_tokens_integration_id", "assignment_integration_tokens", ["integration_id"])


def downgrade() -> None:
    op.drop_table("assignment_integration_tokens")
    op.drop_table("assignment_integrations")
