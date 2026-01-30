"""
RBAC for Agents and Instance Type

- Add agent_permissions to permission_sets (same format as instance_permissions)
- Add instance_type to tool_instances (local/http/custom)
- Seed existing agents as 'denied' in default permission set
- Seed existing instances as 'denied' in default permission set

Revision ID: 0050
Revises: 0049
Create Date: 2026-01-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add agent_permissions to permission_sets
    # Format: {"agent_slug": "allowed" | "denied" | "undefined"}
    op.add_column('permission_sets', sa.Column(
        'agent_permissions',
        postgresql.JSONB,
        server_default='{}',
        nullable=False
    ))
    
    # 2. Add instance_type to tool_instances
    # Types: local (collections, internal), http (external APIs), custom
    op.add_column('tool_instances', sa.Column(
        'instance_type',
        sa.String(20),
        server_default='http',
        nullable=False
    ))
    
    # Set collection instances to 'local' type
    op.execute("""
        UPDATE tool_instances ti
        SET instance_type = 'local'
        FROM tool_groups tg
        WHERE ti.tool_group_id = tg.id AND tg.slug = 'collection'
    """)
    
    # 3. Seed existing agents as 'denied' in default permission set
    # Get default permission set and add all agents
    op.execute("""
        UPDATE permission_sets
        SET agent_permissions = (
            SELECT COALESCE(
                jsonb_object_agg(slug, 'denied'),
                '{}'::jsonb
            )
            FROM agents
        )
        WHERE scope = 'default' 
          AND tenant_id IS NULL 
          AND user_id IS NULL
          AND agent_permissions = '{}'::jsonb
    """)
    
    # 4. Seed existing instances as 'denied' in default permission set (if not already set)
    op.execute("""
        UPDATE permission_sets ps
        SET instance_permissions = ps.instance_permissions || (
            SELECT COALESCE(
                jsonb_object_agg(ti.slug, 'denied'),
                '{}'::jsonb
            )
            FROM tool_instances ti
            WHERE NOT (ps.instance_permissions ? ti.slug)
        )
        WHERE scope = 'default' 
          AND tenant_id IS NULL 
          AND user_id IS NULL
    """)
    
    # 5. Create index for faster lookups
    op.create_index(
        'ix_tool_instances_instance_type',
        'tool_instances',
        ['instance_type']
    )


def downgrade() -> None:
    op.drop_index('ix_tool_instances_instance_type', 'tool_instances')
    op.drop_column('tool_instances', 'instance_type')
    op.drop_column('permission_sets', 'agent_permissions')
