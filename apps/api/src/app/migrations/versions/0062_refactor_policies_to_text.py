"""
Refactor policies: remove numeric limits (moved to limits table),
add policy_text/policy_json fields, rename recommended_version_id to current_version_id,
remove is_active from policies container.

Revision ID: 0062
Revises: 0061
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0062'
down_revision = '0061'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add new columns to policy_versions
    op.add_column('policy_versions', sa.Column('hash', sa.Text, nullable=True, server_default=''))
    op.add_column('policy_versions', sa.Column('policy_text', sa.Text, nullable=True))
    op.add_column('policy_versions', sa.Column('policy_json', postgresql.JSONB, nullable=True))

    # 2. Populate policy_text with a default value for existing versions
    op.execute("""
        UPDATE policy_versions 
        SET policy_text = 'Migrated from numeric limits. Original values: '
            || 'max_steps=' || COALESCE(max_steps::text, 'null')
            || ', max_tool_calls=' || COALESCE(max_tool_calls::text, 'null')
            || ', max_wall_time_ms=' || COALESCE(max_wall_time_ms::text, 'null')
            || ', tool_timeout_ms=' || COALESCE(tool_timeout_ms::text, 'null')
            || ', max_retries=' || COALESCE(max_retries::text, 'null'),
            hash = 'migrated'
        WHERE policy_text IS NULL
    """)

    # 3. Make policy_text NOT NULL
    op.alter_column('policy_versions', 'policy_text', nullable=False)
    op.alter_column('policy_versions', 'hash', nullable=False)

    # 4. Drop numeric limit columns from policy_versions
    op.drop_column('policy_versions', 'max_steps')
    op.drop_column('policy_versions', 'max_tool_calls')
    op.drop_column('policy_versions', 'max_wall_time_ms')
    op.drop_column('policy_versions', 'tool_timeout_ms')
    op.drop_column('policy_versions', 'max_retries')
    op.drop_column('policy_versions', 'budget_tokens')
    op.drop_column('policy_versions', 'budget_cost_cents')
    op.drop_column('policy_versions', 'extra_config')

    # 5. Rename recommended_version_id → current_version_id on policies
    # Drop old FK first
    op.drop_constraint('fk_policies_recommended_version', 'policies', type_='foreignkey')
    op.drop_index('ix_policies_recommended_version_id', 'policies')

    op.alter_column('policies', 'recommended_version_id', new_column_name='current_version_id')

    # Re-create FK and index with new name
    op.create_foreign_key(
        'fk_policies_current_version',
        'policies', 'policy_versions',
        ['current_version_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_policies_current_version_id', 'policies', ['current_version_id'])

    # 6. Drop is_active from policies (no longer needed)
    op.drop_column('policies', 'is_active')

    # 7. Update status values: 'inactive' → 'deprecated'
    op.execute("""
        UPDATE policy_versions 
        SET status = 'deprecated' 
        WHERE status = 'inactive'
    """)


def downgrade() -> None:
    # 1. Add is_active back
    op.add_column('policies', sa.Column('is_active', sa.Boolean, server_default='true'))

    # 2. Rename current_version_id → recommended_version_id
    op.drop_constraint('fk_policies_current_version', 'policies', type_='foreignkey')
    op.drop_index('ix_policies_current_version_id', 'policies')

    op.alter_column('policies', 'current_version_id', new_column_name='recommended_version_id')

    op.create_foreign_key(
        'fk_policies_recommended_version',
        'policies', 'policy_versions',
        ['recommended_version_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_policies_recommended_version_id', 'policies', ['recommended_version_id'])

    # 3. Add back numeric columns to policy_versions
    op.add_column('policy_versions', sa.Column('max_steps', sa.Integer, nullable=True))
    op.add_column('policy_versions', sa.Column('max_tool_calls', sa.Integer, nullable=True))
    op.add_column('policy_versions', sa.Column('max_wall_time_ms', sa.Integer, nullable=True))
    op.add_column('policy_versions', sa.Column('tool_timeout_ms', sa.Integer, nullable=True))
    op.add_column('policy_versions', sa.Column('max_retries', sa.Integer, nullable=True))
    op.add_column('policy_versions', sa.Column('budget_tokens', sa.Integer, nullable=True))
    op.add_column('policy_versions', sa.Column('budget_cost_cents', sa.Integer, nullable=True))
    op.add_column('policy_versions', sa.Column('extra_config', postgresql.JSONB, nullable=False, server_default='{}'))

    # 4. Drop new columns
    op.drop_column('policy_versions', 'policy_json')
    op.drop_column('policy_versions', 'policy_text')
    op.drop_column('policy_versions', 'hash')

    # 5. Revert status values
    op.execute("""
        UPDATE policy_versions 
        SET status = 'inactive' 
        WHERE status = 'deprecated'
    """)
