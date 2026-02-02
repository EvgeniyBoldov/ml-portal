"""
Policy versioning - split policies into container + versions.

This migration:
1. Creates policy_versions table
2. Migrates existing policy data to v1 versions
3. Adds recommended_version_id to policies
4. Removes versioned fields from policies table

Revision ID: 0055
Revises: 0054
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

revision = '0055'
down_revision = '0054'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create policy_versions table
    op.create_table(
        'policy_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('policy_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, default='draft', index=True),
        sa.Column('max_steps', sa.Integer(), nullable=True),
        sa.Column('max_tool_calls', sa.Integer(), nullable=True),
        sa.Column('max_wall_time_ms', sa.Integer(), nullable=True),
        sa.Column('tool_timeout_ms', sa.Integer(), nullable=True),
        sa.Column('max_retries', sa.Integer(), nullable=True),
        sa.Column('budget_tokens', sa.Integer(), nullable=True),
        sa.Column('budget_cost_cents', sa.Integer(), nullable=True),
        sa.Column('extra_config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('parent_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['policy_id'], ['policies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_version_id'], ['policy_versions.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('policy_id', 'version', name='uix_policy_version'),
    )
    
    # 2. Add recommended_version_id column to policies FIRST
    op.add_column('policies', sa.Column(
        'recommended_version_id', 
        postgresql.UUID(as_uuid=True), 
        nullable=True
    ))
    op.create_index('ix_policies_recommended_version_id', 'policies', ['recommended_version_id'])
    
    # 3. Migrate existing policies to v1 versions
    connection = op.get_bind()
    policies = connection.execute(
        sa.text("""
            SELECT id, max_steps, max_tool_calls, max_wall_time_ms, 
                   tool_timeout_ms, max_retries, budget_tokens, budget_cost_cents, 
                   extra_config, created_at
            FROM policies
        """)
    ).fetchall()
    
    for policy in policies:
        version_id = uuid.uuid4()
        connection.execute(
            sa.text("""
                INSERT INTO policy_versions 
                (id, policy_id, version, status, max_steps, max_tool_calls, max_wall_time_ms,
                 tool_timeout_ms, max_retries, budget_tokens, budget_cost_cents, extra_config,
                 created_at, updated_at)
                VALUES 
                (:id, :policy_id, 1, 'active', :max_steps, :max_tool_calls, :max_wall_time_ms,
                 :tool_timeout_ms, :max_retries, :budget_tokens, :budget_cost_cents, :extra_config,
                 :created_at, :created_at)
            """),
            {
                'id': str(version_id),
                'policy_id': str(policy.id),
                'max_steps': policy.max_steps,
                'max_tool_calls': policy.max_tool_calls,
                'max_wall_time_ms': policy.max_wall_time_ms,
                'tool_timeout_ms': policy.tool_timeout_ms,
                'max_retries': policy.max_retries,
                'budget_tokens': policy.budget_tokens,
                'budget_cost_cents': policy.budget_cost_cents,
                'extra_config': policy.extra_config if policy.extra_config else '{}',
                'created_at': policy.created_at,
            }
        )
        
        # Update policy with recommended_version_id
        connection.execute(
            sa.text("""
                UPDATE policies SET recommended_version_id = :version_id WHERE id = :policy_id
            """),
            {'version_id': str(version_id), 'policy_id': str(policy.id)}
        )
    
    # 4. Add foreign key constraint for recommended_version_id
    op.create_foreign_key(
        'fk_policies_recommended_version',
        'policies', 'policy_versions',
        ['recommended_version_id'], ['id'],
        ondelete='SET NULL'
    )
    
    # 5. Drop versioned columns from policies table
    op.drop_column('policies', 'max_steps')
    op.drop_column('policies', 'max_tool_calls')
    op.drop_column('policies', 'max_wall_time_ms')
    op.drop_column('policies', 'tool_timeout_ms')
    op.drop_column('policies', 'max_retries')
    op.drop_column('policies', 'budget_tokens')
    op.drop_column('policies', 'budget_cost_cents')
    op.drop_column('policies', 'extra_config')


def downgrade() -> None:
    # 1. Add back versioned columns to policies
    op.add_column('policies', sa.Column('max_steps', sa.Integer(), nullable=True))
    op.add_column('policies', sa.Column('max_tool_calls', sa.Integer(), nullable=True))
    op.add_column('policies', sa.Column('max_wall_time_ms', sa.Integer(), nullable=True))
    op.add_column('policies', sa.Column('tool_timeout_ms', sa.Integer(), nullable=True))
    op.add_column('policies', sa.Column('max_retries', sa.Integer(), nullable=True))
    op.add_column('policies', sa.Column('budget_tokens', sa.Integer(), nullable=True))
    op.add_column('policies', sa.Column('budget_cost_cents', sa.Integer(), nullable=True))
    op.add_column('policies', sa.Column('extra_config', postgresql.JSONB(), nullable=False, server_default='{}'))
    
    # 2. Migrate data back from active versions
    connection = op.get_bind()
    connection.execute(
        sa.text("""
            UPDATE policies p
            SET max_steps = pv.max_steps,
                max_tool_calls = pv.max_tool_calls,
                max_wall_time_ms = pv.max_wall_time_ms,
                tool_timeout_ms = pv.tool_timeout_ms,
                max_retries = pv.max_retries,
                budget_tokens = pv.budget_tokens,
                budget_cost_cents = pv.budget_cost_cents,
                extra_config = pv.extra_config
            FROM policy_versions pv
            WHERE pv.id = p.recommended_version_id
        """)
    )
    
    # 3. Drop foreign key and column
    op.drop_constraint('fk_policies_recommended_version', 'policies', type_='foreignkey')
    op.drop_column('policies', 'recommended_version_id')
    
    # 4. Drop policy_versions table
    op.drop_table('policy_versions')
