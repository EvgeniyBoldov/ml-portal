"""
Tool Groups and Agent Bindings architecture refactor

- Create tool_groups table
- Add tool_group_id FK to tools (replace tool_type string)
- Update tool_instances: remove scope/tenant_id/user_id, add tool_group_id FK, add metadata
- Create agent_bindings table
- Remove legacy fields from agents

Revision ID: 0047
Revises: 0046
Create Date: 2025-01-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create tool_groups table
    op.create_table(
        "tool_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(50), unique=True, index=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # 2. Seed default tool groups from existing tool_type values
    op.execute("""
        INSERT INTO tool_groups (id, slug, name, description)
        SELECT DISTINCT
            gen_random_uuid(),
            tool_type,
            INITCAP(tool_type),
            'Auto-generated from tool_type'
        FROM tools
        WHERE tool_type IS NOT NULL
        ON CONFLICT (slug) DO NOTHING
    """)
    
    # Also seed common groups if not exists
    op.execute("""
        INSERT INTO tool_groups (id, slug, name, description) VALUES
            (gen_random_uuid(), 'rag', 'RAG', 'Retrieval Augmented Generation'),
            (gen_random_uuid(), 'collection', 'Collections', 'Structured data collections'),
            (gen_random_uuid(), 'jira', 'Jira', 'Jira issue tracking'),
            (gen_random_uuid(), 'netbox', 'NetBox', 'Network documentation'),
            (gen_random_uuid(), 'cmdb', 'CMDB', 'Configuration Management Database'),
            (gen_random_uuid(), 'remedy', 'Remedy', 'BMC Remedy ITSM')
        ON CONFLICT (slug) DO NOTHING
    """)
    
    # 3. Add tool_group_id to tools table
    op.add_column("tools", sa.Column("tool_group_id", postgresql.UUID(as_uuid=True), nullable=True))
    
    # Populate tool_group_id from tool_type
    op.execute("""
        UPDATE tools t
        SET tool_group_id = tg.id
        FROM tool_groups tg
        WHERE t.tool_type = tg.slug
    """)
    
    # Make tool_group_id NOT NULL and add FK
    op.alter_column("tools", "tool_group_id", nullable=False)
    op.create_foreign_key("fk_tools_tool_group", "tools", "tool_groups", ["tool_group_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_tools_tool_group_id", "tools", ["tool_group_id"])
    
    # Drop old tool_type column
    op.drop_column("tools", "tool_type")
    
    # 4. Update tool_instances table
    # Add tool_group_id column
    op.add_column("tool_instances", sa.Column("tool_group_id", postgresql.UUID(as_uuid=True), nullable=True))
    
    # Add instance_metadata column
    op.add_column("tool_instances", sa.Column("instance_metadata", postgresql.JSONB, server_default='{}', nullable=False))
    
    # Populate tool_group_id from tool_type
    op.execute("""
        UPDATE tool_instances ti
        SET tool_group_id = tg.id
        FROM tool_groups tg
        WHERE ti.tool_type = tg.slug
    """)
    
    # For instances without matching group, create one
    op.execute("""
        INSERT INTO tool_groups (id, slug, name, description)
        SELECT DISTINCT
            gen_random_uuid(),
            ti.tool_type,
            INITCAP(ti.tool_type),
            'Auto-generated from tool_instance'
        FROM tool_instances ti
        WHERE ti.tool_group_id IS NULL AND ti.tool_type IS NOT NULL
        ON CONFLICT (slug) DO NOTHING
    """)
    
    # Update again after creating missing groups
    op.execute("""
        UPDATE tool_instances ti
        SET tool_group_id = tg.id
        FROM tool_groups tg
        WHERE ti.tool_type = tg.slug AND ti.tool_group_id IS NULL
    """)
    
    # Make tool_group_id NOT NULL and add FK
    op.alter_column("tool_instances", "tool_group_id", nullable=False)
    op.create_foreign_key("fk_tool_instances_tool_group", "tool_instances", "tool_groups", ["tool_group_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_tool_instances_tool_group_id", "tool_instances", ["tool_group_id"])
    
    # Drop old columns from tool_instances
    op.drop_constraint("tool_instances_scope_check", "tool_instances", type_="check")
    op.drop_constraint("tool_instances_scope_refs_check", "tool_instances", type_="check")
    op.drop_column("tool_instances", "tool_type")
    op.drop_column("tool_instances", "scope")
    op.drop_column("tool_instances", "tenant_id")
    op.drop_column("tool_instances", "user_id")
    op.drop_column("tool_instances", "is_default")
    
    # 5. Create agent_bindings table
    op.create_table(
        "agent_bindings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tool_instance_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tool_instances.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("credential_strategy", sa.String(20), default="any", nullable=False),
        sa.Column("required", sa.Boolean, default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint("agent_id", "tool_id", name="uq_agent_tool"),
    )
    
    # 6. Remove legacy fields from agents
    op.drop_column("agents", "tools")
    op.drop_column("agents", "available_collections")
    op.drop_column("agents", "tools_config")
    op.drop_column("agents", "collections_config")
    op.drop_column("agents", "tool_bindings")
    op.drop_column("agents", "policy")


def downgrade() -> None:
    # 1. Restore legacy fields to agents
    op.add_column("agents", sa.Column("tools", postgresql.JSONB, server_default='[]', nullable=False))
    op.add_column("agents", sa.Column("available_collections", postgresql.JSONB, server_default='[]', nullable=False))
    op.add_column("agents", sa.Column("tools_config", postgresql.JSONB, server_default='[]', nullable=False))
    op.add_column("agents", sa.Column("collections_config", postgresql.JSONB, server_default='[]', nullable=False))
    op.add_column("agents", sa.Column("tool_bindings", postgresql.JSONB, server_default='[]', nullable=False))
    op.add_column("agents", sa.Column("policy", postgresql.JSONB, server_default='{}', nullable=False))
    
    # 2. Drop agent_bindings table
    op.drop_table("agent_bindings")
    
    # 3. Restore tool_instances columns
    op.add_column("tool_instances", sa.Column("tool_type", sa.String(50), nullable=True))
    op.add_column("tool_instances", sa.Column("scope", sa.String(20), nullable=True))
    op.add_column("tool_instances", sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tool_instances", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("tool_instances", sa.Column("is_default", sa.Boolean, default=False))
    
    # Populate tool_type from tool_group
    op.execute("""
        UPDATE tool_instances ti
        SET tool_type = tg.slug
        FROM tool_groups tg
        WHERE ti.tool_group_id = tg.id
    """)
    
    # Set default scope
    op.execute("UPDATE tool_instances SET scope = 'default' WHERE scope IS NULL")
    
    op.alter_column("tool_instances", "tool_type", nullable=False)
    op.alter_column("tool_instances", "scope", nullable=False)
    
    # Restore constraints
    op.create_check_constraint("tool_instances_scope_check", "tool_instances", "scope IN ('default', 'tenant', 'user')")
    op.create_check_constraint(
        "tool_instances_scope_refs_check", 
        "tool_instances",
        """
        (scope = 'default' AND tenant_id IS NULL AND user_id IS NULL) OR
        (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL) OR
        (scope = 'user' AND tenant_id IS NOT NULL AND user_id IS NOT NULL)
        """
    )
    
    # Drop new columns
    op.drop_constraint("fk_tool_instances_tool_group", "tool_instances", type_="foreignkey")
    op.drop_index("ix_tool_instances_tool_group_id", "tool_instances")
    op.drop_column("tool_instances", "tool_group_id")
    op.drop_column("tool_instances", "instance_metadata")
    
    # 4. Restore tools columns
    op.add_column("tools", sa.Column("tool_type", sa.String(50), nullable=True))
    
    # Populate tool_type from tool_group
    op.execute("""
        UPDATE tools t
        SET tool_type = tg.slug
        FROM tool_groups tg
        WHERE t.tool_group_id = tg.id
    """)
    
    op.alter_column("tools", "tool_type", nullable=False)
    op.create_index("ix_tools_tool_type", "tools", ["tool_type"])
    
    # Drop FK and column
    op.drop_constraint("fk_tools_tool_group", "tools", type_="foreignkey")
    op.drop_index("ix_tools_tool_group_id", "tools")
    op.drop_column("tools", "tool_group_id")
    
    # 5. Drop tool_groups table
    op.drop_table("tool_groups")
