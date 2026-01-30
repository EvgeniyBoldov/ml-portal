"""
RBAC and Policy refactor:
- Add tool_type to tools table
- Change tool_instances to use tool_type instead of tool_id
- Refactor permission_sets to RBAC on instances
- Add default scope to credential_sets
- Create policies table
- Add tool_bindings and policy_id to agents

Revision ID: 0046_rbac_and_policy_refactor
Revises: 0045_split_prompts_to_container_and_versions
Create Date: 2026-01-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0046'
down_revision = '0045'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add tool_type to tools table
    op.add_column('tools', sa.Column('tool_type', sa.String(50), nullable=True))
    
    # Populate tool_type from slug (first part before dot)
    op.execute("""
        UPDATE tools 
        SET tool_type = SPLIT_PART(slug, '.', 1)
        WHERE tool_type IS NULL
    """)
    
    # Make tool_type NOT NULL after population
    op.alter_column('tools', 'tool_type', nullable=False)
    op.create_index('ix_tools_tool_type', 'tools', ['tool_type'])

    # 2. Modify tool_instances: replace tool_id with tool_type
    # First add tool_type column
    op.add_column('tool_instances', sa.Column('tool_type', sa.String(50), nullable=True))
    
    # Populate tool_type from existing tool_id
    op.execute("""
        UPDATE tool_instances ti
        SET tool_type = t.tool_type
        FROM tools t
        WHERE ti.tool_id = t.id
    """)
    
    # For any orphaned instances, extract from slug
    op.execute("""
        UPDATE tool_instances 
        SET tool_type = SPLIT_PART(slug, '-', 1)
        WHERE tool_type IS NULL
    """)
    
    # Make tool_type NOT NULL
    op.alter_column('tool_instances', 'tool_type', nullable=False)
    op.create_index('ix_tool_instances_tool_type', 'tool_instances', ['tool_type'])
    
    # Drop old tool_id foreign key and column
    op.drop_constraint('tool_instances_tool_id_fkey', 'tool_instances', type_='foreignkey')
    op.drop_index('ix_tool_instances_tool_id', 'tool_instances')
    op.drop_column('tool_instances', 'tool_id')

    # 3. Refactor permission_sets to RBAC on instances
    # Drop old columns
    op.drop_column('permission_sets', 'allowed_tools')
    op.drop_column('permission_sets', 'denied_tools')
    op.drop_column('permission_sets', 'allowed_collections')
    op.drop_column('permission_sets', 'denied_collections')
    
    # Add new instance_permissions column
    # Format: {"instance_slug": "allowed" | "denied" | "undefined"}
    op.add_column('permission_sets', sa.Column(
        'instance_permissions', 
        postgresql.JSONB, 
        server_default='{}',
        nullable=False
    ))

    # 4. Add default scope to credential_sets
    # Drop old constraint
    op.drop_constraint('credential_sets_scope_check', 'credential_sets', type_='check')
    op.drop_constraint('credential_sets_scope_refs_check', 'credential_sets', type_='check')
    
    # Add new constraints with default scope
    op.create_check_constraint(
        'credential_sets_scope_check',
        'credential_sets',
        "scope IN ('default', 'tenant', 'user')"
    )
    op.create_check_constraint(
        'credential_sets_scope_refs_check',
        'credential_sets',
        """
        (scope = 'default' AND tenant_id IS NULL AND user_id IS NULL) OR
        (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL) OR
        (scope = 'user' AND tenant_id IS NOT NULL AND user_id IS NOT NULL)
        """
    )

    # 5. Create policies table
    op.create_table(
        'policies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('slug', sa.String(255), unique=True, index=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        
        # Numeric limits
        sa.Column('max_steps', sa.Integer, nullable=True),
        sa.Column('max_tool_calls', sa.Integer, nullable=True),
        sa.Column('max_wall_time_ms', sa.Integer, nullable=True),
        sa.Column('tool_timeout_ms', sa.Integer, nullable=True),
        sa.Column('max_retries', sa.Integer, nullable=True),
        sa.Column('budget_tokens', sa.Integer, nullable=True),
        sa.Column('budget_cost_cents', sa.Integer, nullable=True),
        
        # Extended config as JSON
        sa.Column('extra_config', postgresql.JSONB, server_default='{}', nullable=False),
        
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Seed default policy
    op.execute("""
        INSERT INTO policies (slug, name, description, max_steps, max_tool_calls, max_wall_time_ms, tool_timeout_ms, max_retries)
        VALUES ('default', 'Default Policy', 'Standard execution limits', 20, 50, 300000, 30000, 3)
    """)

    # 6. Add policy_id and tool_bindings to agents
    op.add_column('agents', sa.Column(
        'policy_id', 
        postgresql.UUID(as_uuid=True), 
        sa.ForeignKey('policies.id', ondelete='SET NULL'),
        nullable=True
    ))
    
    # tool_bindings format:
    # [{"tool_slug": "jira.create", "instance_slug": "jira-prod", "credential_strategy": "user_only"}]
    op.add_column('agents', sa.Column(
        'tool_bindings',
        postgresql.JSONB,
        server_default='[]',
        nullable=False
    ))
    
    # Set default policy for existing agents
    op.execute("""
        UPDATE agents 
        SET policy_id = (SELECT id FROM policies WHERE slug = 'default')
        WHERE policy_id IS NULL
    """)
    
    # Create index for policy_id
    op.create_index('ix_agents_policy_id', 'agents', ['policy_id'])


def downgrade() -> None:
    # Remove from agents
    op.drop_index('ix_agents_policy_id', 'agents')
    op.drop_column('agents', 'tool_bindings')
    op.drop_column('agents', 'policy_id')
    
    # Drop policies table
    op.drop_table('policies')
    
    # Restore credential_sets constraints
    op.drop_constraint('credential_sets_scope_check', 'credential_sets', type_='check')
    op.drop_constraint('credential_sets_scope_refs_check', 'credential_sets', type_='check')
    op.create_check_constraint(
        'credential_sets_scope_check',
        'credential_sets',
        "scope IN ('tenant', 'user')"
    )
    op.create_check_constraint(
        'credential_sets_scope_refs_check',
        'credential_sets',
        """
        (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL) OR
        (scope = 'user' AND tenant_id IS NOT NULL AND user_id IS NOT NULL)
        """
    )
    
    # Restore permission_sets columns
    op.drop_column('permission_sets', 'instance_permissions')
    op.add_column('permission_sets', sa.Column('allowed_tools', postgresql.JSONB, server_default='[]'))
    op.add_column('permission_sets', sa.Column('denied_tools', postgresql.JSONB, server_default='[]'))
    op.add_column('permission_sets', sa.Column('allowed_collections', postgresql.JSONB, server_default='[]'))
    op.add_column('permission_sets', sa.Column('denied_collections', postgresql.JSONB, server_default='[]'))
    
    # Restore tool_instances.tool_id
    op.add_column('tool_instances', sa.Column('tool_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index('ix_tool_instances_tool_id', 'tool_instances', ['tool_id'])
    op.create_foreign_key('tool_instances_tool_id_fkey', 'tool_instances', 'tools', ['tool_id'], ['id'], ondelete='CASCADE')
    op.drop_index('ix_tool_instances_tool_type', 'tool_instances')
    op.drop_column('tool_instances', 'tool_type')
    
    # Remove tool_type from tools
    op.drop_index('ix_tools_tool_type', 'tools')
    op.drop_column('tools', 'tool_type')
