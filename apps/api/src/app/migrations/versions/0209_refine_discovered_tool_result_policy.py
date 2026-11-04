"""Keep Store for list results and Direct for singleton/catalog results.

Revision ID: 0209
Revises: 0208
"""
from alembic import op


revision = "0209"
down_revision = "0208"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # These capabilities return one object or bounded schema/catalog metadata.
    # The operator can still explicitly opt a particular provider instance in
    # to Store after reviewing its observed schema.
    op.execute("""
        UPDATE discovered_tools
        SET result_delivery = 'direct'
        WHERE source IN ('mcp', 'local')
          AND slug IN (
              'netbox_get_device',
              'collection.get',
              'collection.table.get',
              'search_objects',
              'sql.search_objects',
              'collection.sql.search_objects'
          )
    """)

    # Keep records, issue pages and SQL rows addressable through the workspace.
    # Jira aliases are included for both the legacy shim and the active adapter.
    op.execute("""
        UPDATE discovered_tools
        SET result_delivery = 'store'
        WHERE source IN ('mcp', 'local')
          AND slug IN (
              'netbox_get_objects',
              'netbox_search_objects',
              'netbox_search_devices',
              'netbox_list_sites',
              'jira_search_issues',
              'jira_search',
              'jira_get_project_issues',
              'jira_list_issues',
              'jira_list_projects',
              'jira_get_issue',
              'execute_sql',
              'sql.execute_sql',
              'collection_search',
              'collection.search',
              'collection.aggregate',
              'collection.table.search',
              'collection.table.aggregate'
          )
    """)


def downgrade() -> None:
    # Restore the previous 0208 policy for the capabilities reclassified here.
    op.execute("""
        UPDATE discovered_tools
        SET result_delivery = 'store'
        WHERE source IN ('mcp', 'local')
          AND slug IN (
              'netbox_get_device',
              'collection.get',
              'collection.table.get',
              'search_objects',
              'sql.search_objects',
              'collection.sql.search_objects'
          )
    """)
    op.execute("""
        UPDATE discovered_tools
        SET result_delivery = 'direct'
        WHERE source IN ('mcp', 'local')
          AND slug = 'jira_search'
    """)
