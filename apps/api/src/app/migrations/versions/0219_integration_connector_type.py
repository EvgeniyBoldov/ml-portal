"""Allow integration connectors in the shared connector registry."""

from alembic import op

revision = "0219"
down_revision = "0218"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_connector_type", "tool_instances", type_="check")
    op.create_check_constraint(
        "ck_connector_type",
        "tool_instances",
        "connector_type IN ('data', 'mcp', 'model', 'integration')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_connector_type", "tool_instances", type_="check")
    op.create_check_constraint(
        "ck_connector_type",
        "tool_instances",
        "connector_type IN ('data', 'mcp', 'model')",
    )
