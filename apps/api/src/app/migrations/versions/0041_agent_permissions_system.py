"""
Agent permissions system - tool instances, credentials, permission sets

Revision ID: 0041
Revises: 0040
Create Date: 2026-01-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0041'
down_revision = '0040'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create tool_instances table
    op.create_table(
        'tool_instances',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tool_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tools.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('slug', sa.String(255), unique=True, index=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('scope', sa.String(20), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('connection_config', postgresql.JSONB, server_default='{}', nullable=False),
        sa.Column('is_default', sa.Boolean, server_default='false'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('health_status', sa.String(20), server_default="'unknown'"),
        sa.Column('last_health_check_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('health_check_error', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "scope IN ('default', 'tenant', 'user')",
            name='tool_instances_scope_check'
        ),
        sa.CheckConstraint(
            """
            (scope = 'default' AND tenant_id IS NULL AND user_id IS NULL) OR
            (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL) OR
            (scope = 'user' AND tenant_id IS NOT NULL AND user_id IS NOT NULL)
            """,
            name='tool_instances_scope_refs_check'
        ),
    )

    # 2. Create credential_sets table
    op.create_table(
        'credential_sets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('tool_instance_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tool_instances.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('scope', sa.String(20), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('auth_type', sa.String(50), nullable=False),
        sa.Column('encrypted_payload', sa.Text, nullable=False),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "scope IN ('tenant', 'user')",
            name='credential_sets_scope_check'
        ),
        sa.CheckConstraint(
            """
            (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL) OR
            (scope = 'user' AND tenant_id IS NOT NULL AND user_id IS NOT NULL)
            """,
            name='credential_sets_scope_refs_check'
        ),
        sa.CheckConstraint(
            "auth_type IN ('token', 'basic', 'oauth', 'api_key')",
            name='credential_sets_auth_type_check'
        ),
    )

    # 3. Create permission_sets table
    op.create_table(
        'permission_sets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('scope', sa.String(20), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('allowed_tools', postgresql.JSONB, server_default='[]'),
        sa.Column('denied_tools', postgresql.JSONB, server_default='[]'),
        sa.Column('allowed_collections', postgresql.JSONB, server_default='[]'),
        sa.Column('denied_collections', postgresql.JSONB, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "scope IN ('default', 'tenant', 'user')",
            name='permission_sets_scope_check'
        ),
        sa.CheckConstraint(
            """
            (scope = 'default' AND tenant_id IS NULL AND user_id IS NULL) OR
            (scope = 'tenant' AND tenant_id IS NOT NULL AND user_id IS NULL) OR
            (scope = 'user' AND tenant_id IS NOT NULL AND user_id IS NOT NULL)
            """,
            name='permission_sets_scope_refs_check'
        ),
        sa.UniqueConstraint('scope', 'tenant_id', 'user_id', name='uix_permission_sets_scope'),
    )

    # 4. Create routing_logs table
    op.create_table(
        'routing_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('run_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('request_text', sa.Text, nullable=True),
        sa.Column('intent', sa.String(50), nullable=True),
        sa.Column('intent_confidence', sa.Float, nullable=True),
        sa.Column('selected_agent_slug', sa.String(255), nullable=True),
        sa.Column('agent_confidence', sa.Float, nullable=True),
        sa.Column('routing_reasons', postgresql.JSONB, server_default='[]'),
        sa.Column('missing_tools', postgresql.JSONB, server_default='[]'),
        sa.Column('missing_collections', postgresql.JSONB, server_default='[]'),
        sa.Column('missing_credentials', postgresql.JSONB, server_default='[]'),
        sa.Column('execution_mode', sa.String(20), nullable=True),
        sa.Column('effective_tools', postgresql.JSONB, server_default='[]'),
        sa.Column('effective_collections', postgresql.JSONB, server_default='[]'),
        sa.Column('tool_instances_map', postgresql.JSONB, server_default='{}'),
        sa.Column('routed_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('routing_duration_ms', sa.Integer, nullable=True),
        sa.Column('status', sa.String(50), server_default="'pending'"),
        sa.Column('error_message', sa.Text, nullable=True),
    )

    # 5. Add new columns to agents table
    op.add_column('agents', sa.Column('tools_config', postgresql.JSONB, server_default='[]'))
    op.add_column('agents', sa.Column('collections_config', postgresql.JSONB, server_default='[]'))
    op.add_column('agents', sa.Column('policy', postgresql.JSONB, server_default='{}'))
    op.add_column('agents', sa.Column('capabilities', postgresql.JSONB, server_default='[]'))
    op.add_column('agents', sa.Column('supports_partial_mode', sa.Boolean, server_default='false'))

    # 6. Create default permission set (allows all tools by default)
    op.execute("""
        INSERT INTO permission_sets (scope, allowed_tools, allowed_collections)
        VALUES ('default', '["rag.search", "collection.search"]', '[]')
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    # Remove columns from agents
    op.drop_column('agents', 'supports_partial_mode')
    op.drop_column('agents', 'capabilities')
    op.drop_column('agents', 'policy')
    op.drop_column('agents', 'collections_config')
    op.drop_column('agents', 'tools_config')

    # Drop tables in reverse order
    op.drop_table('routing_logs')
    op.drop_table('permission_sets')
    op.drop_table('credential_sets')
    op.drop_table('tool_instances')
