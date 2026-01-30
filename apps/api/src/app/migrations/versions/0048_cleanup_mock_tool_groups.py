"""
Cleanup mock tool groups

Remove tool groups that were seeded in migration 0047 but don't have any tools.
Keep only groups that have actual tools (rag, collection).

Revision ID: 0048
Revises: 0047
Create Date: 2025-01-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Delete tool groups that have no tools
    op.execute("""
        DELETE FROM tool_groups
        WHERE id NOT IN (
            SELECT DISTINCT tool_group_id FROM tools WHERE tool_group_id IS NOT NULL
        )
        AND id NOT IN (
            SELECT DISTINCT tool_group_id FROM tool_instances WHERE tool_group_id IS NOT NULL
        )
    """)


def downgrade() -> None:
    # Re-seed the mock groups if needed
    op.execute("""
        INSERT INTO tool_groups (id, slug, name, description) VALUES
            (gen_random_uuid(), 'jira', 'Jira', 'Jira issue tracking'),
            (gen_random_uuid(), 'netbox', 'NetBox', 'Network documentation'),
            (gen_random_uuid(), 'cmdb', 'CMDB', 'Configuration Management Database'),
            (gen_random_uuid(), 'remedy', 'Remedy', 'BMC Remedy ITSM')
        ON CONFLICT (slug) DO NOTHING
    """)
