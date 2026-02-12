"""
Add instance_type (local/remote) and slug to tool_instances.
Flatten RBAC: remove rbac_policies container, keep rbac_rules with direct owner binding.

Revision ID: 0042_instance_type_rbac
Revises: 0041_agent_permissions_system
Create Date: 2026-02-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0042_instance_type_rbac'
down_revision = '0041_agent_permissions_system'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── 1. tool_instances: add slug, instance_type ─────────────────────

    # Add slug column (nullable first, then populate, then make NOT NULL)
    op.add_column('tool_instances', sa.Column('slug', sa.String(255), nullable=True))
    
    # Add instance_type column with default 'remote'
    op.add_column('tool_instances', sa.Column(
        'instance_type', sa.String(20), nullable=False, server_default='remote'
    ))
    
    # Populate slug from name (slugified: lowercase, spaces→dashes)
    op.execute("""
        UPDATE tool_instances
        SET slug = LOWER(REPLACE(REPLACE(name, ' ', '-'), ':', '-'))
        WHERE slug IS NULL
    """)
    
    # Mark existing collection instances as local
    op.execute("""
        UPDATE tool_instances ti
        SET instance_type = 'local'
        FROM tool_groups tg
        WHERE ti.tool_group_id = tg.id
          AND tg.slug IN ('collection', 'rag')
    """)
    
    # Make slug NOT NULL
    op.alter_column('tool_instances', 'slug', nullable=False)
    
    # Add index on slug
    op.create_index('ix_tool_instances_slug', 'tool_instances', ['slug'])
    
    # Drop old unique constraint on (tool_group_id, url)
    op.execute("ALTER TABLE tool_instances DROP CONSTRAINT IF EXISTS uq_tool_instance_group_url")
    
    # Add new unique constraint on (tool_group_id, slug)
    op.create_unique_constraint(
        'uq_tool_instance_group_slug', 'tool_instances', ['tool_group_id', 'slug']
    )
    
    # Add check constraint for instance_type
    op.create_check_constraint(
        'ck_tool_instance_type', 'tool_instances',
        "instance_type IN ('local', 'remote')"
    )

    # ─── 2. RBAC flatten: remove rbac_policies, restructure rbac_rules ──

    # Add direct owner columns to rbac_rules
    op.add_column('rbac_rules', sa.Column(
        'owner_user_id', postgresql.UUID(as_uuid=True),
        sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True
    ))
    op.add_column('rbac_rules', sa.Column(
        'owner_tenant_id', postgresql.UUID(as_uuid=True),
        sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True
    ))
    op.add_column('rbac_rules', sa.Column(
        'owner_platform', sa.Boolean(), nullable=False, server_default='false'
    ))
    
    # Migrate data: copy level/level_id to owner columns
    op.execute("""
        UPDATE rbac_rules
        SET owner_user_id = level_id
        WHERE level = 'user'
    """)
    op.execute("""
        UPDATE rbac_rules
        SET owner_tenant_id = level_id
        WHERE level = 'tenant'
    """)
    op.execute("""
        UPDATE rbac_rules
        SET owner_platform = true
        WHERE level = 'platform'
    """)
    
    # Drop old constraints that reference rbac_policy_id
    op.execute("ALTER TABLE rbac_rules DROP CONSTRAINT IF EXISTS uq_rbac_rule_unique")
    op.execute("ALTER TABLE rbac_rules DROP CONSTRAINT IF EXISTS ck_rbac_rule_level_id")
    
    # Drop FK to rbac_policies
    op.execute("ALTER TABLE rbac_rules DROP CONSTRAINT IF EXISTS rbac_rules_rbac_policy_id_fkey")
    
    # Drop old columns
    op.drop_column('rbac_rules', 'rbac_policy_id')
    op.drop_column('rbac_rules', 'level_id')
    
    # Add new unique constraint
    op.create_unique_constraint(
        'uq_rbac_rule_owner_resource',
        'rbac_rules',
        ['level', 'owner_user_id', 'owner_tenant_id', 'owner_platform', 'resource_type', 'resource_id']
    )
    
    # Add check: exactly one owner must be set
    op.create_check_constraint(
        'ck_rbac_rule_single_owner',
        'rbac_rules',
        """
        (owner_platform::int +
         (owner_user_id IS NOT NULL)::int +
         (owner_tenant_id IS NOT NULL)::int) = 1
        """
    )
    
    # Add indexes for owner lookups
    op.create_index('ix_rbac_rules_owner_user', 'rbac_rules', ['owner_user_id'],
                    postgresql_where=sa.text('owner_user_id IS NOT NULL'))
    op.create_index('ix_rbac_rules_owner_tenant', 'rbac_rules', ['owner_tenant_id'],
                    postgresql_where=sa.text('owner_tenant_id IS NOT NULL'))
    op.create_index('ix_rbac_rules_owner_platform', 'rbac_rules', ['owner_platform'],
                    postgresql_where=sa.text('owner_platform = true'))
    
    # Drop default_rbac_policy_id from platform_settings (FK to rbac_policies)
    op.execute("ALTER TABLE platform_settings DROP CONSTRAINT IF EXISTS platform_settings_default_rbac_policy_id_fkey")
    op.drop_column('platform_settings', 'default_rbac_policy_id')
    
    # Drop rbac_policies table (container no longer needed)
    op.drop_table('rbac_policies')


def downgrade() -> None:
    # Recreate rbac_policies
    op.create_table(
        'rbac_policies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slug', sa.String(255), unique=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    
    # Reverse RBAC changes
    op.add_column('rbac_rules', sa.Column('rbac_policy_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('rbac_rules', sa.Column('level_id', postgresql.UUID(as_uuid=True), nullable=True))
    
    op.drop_constraint('ck_rbac_rule_single_owner', 'rbac_rules')
    op.drop_constraint('uq_rbac_rule_owner_resource', 'rbac_rules')
    op.drop_index('ix_rbac_rules_owner_user', 'rbac_rules')
    op.drop_index('ix_rbac_rules_owner_tenant', 'rbac_rules')
    op.drop_index('ix_rbac_rules_owner_platform', 'rbac_rules')
    
    op.drop_column('rbac_rules', 'owner_user_id')
    op.drop_column('rbac_rules', 'owner_tenant_id')
    op.drop_column('rbac_rules', 'owner_platform')
    
    # Reverse tool_instances changes
    op.drop_constraint('ck_tool_instance_type', 'tool_instances')
    op.drop_constraint('uq_tool_instance_group_slug', 'tool_instances')
    op.drop_index('ix_tool_instances_slug', 'tool_instances')
    op.drop_column('tool_instances', 'instance_type')
    op.drop_column('tool_instances', 'slug')
