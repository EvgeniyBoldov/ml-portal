"""Add result delivery policy and observed data schema to discovered tools.

Revision ID: 0208
Revises: 0207
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0208"
down_revision = "0207"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discovered_tools",
        sa.Column("result_delivery", sa.String(length=16), nullable=False, server_default="direct"),
    )
    op.add_column(
        "discovered_tools",
        sa.Column("observed_data_schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_check_constraint(
        "ck_discovered_tools_result_delivery",
        "discovered_tools",
        "result_delivery IN ('direct', 'store')",
    )

    # Preserve only the dataset-backed source operations that have established
    # Result Store readers/adapters. Everything else, including new discoveries,
    # defaults to direct delivery. Keep this list explicit and provider-neutral;
    # the raw capability slug is already scoped by source/provider uniqueness.
    op.execute("""
        UPDATE discovered_tools
        SET result_delivery = 'store'
        WHERE
            (source = 'mcp' AND slug IN (
                'netbox_search_objects',
                'netbox_get_objects',
                'netbox_get_device',
                'netbox_search_devices',
                'netbox_list_sites',
                'jira_search_issues',
                'jira_get_issue',
                'jira_get_project_issues',
                'jira_list_issues',
                'jira_list_projects',
                'execute_sql',
                'sql.execute_sql',
                'search_objects',
                'sql.search_objects',
                'collection_search'
            ))
            OR (source IN ('mcp', 'local') AND slug IN (
                'collection.search',
                'collection.aggregate',
                'collection.get',
                'collection.table.search',
                'collection.table.aggregate',
                'collection.table.get'
            ))
    """)


def downgrade() -> None:
    op.drop_constraint("ck_discovered_tools_result_delivery", "discovered_tools", type_="check")
    op.drop_column("discovered_tools", "observed_data_schema")
    op.drop_column("discovered_tools", "result_delivery")
