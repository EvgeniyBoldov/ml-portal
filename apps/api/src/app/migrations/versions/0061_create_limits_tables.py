"""
Create limits and limit_versions tables.

Limits are execution constraints for agents (max_steps, timeouts, etc.).
Previously this data lived in policies table - now separated into its own entity.

Revision ID: 0061
Revises: 0060
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0061'
down_revision = '0060'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create limits table (container)
    op.create_table(
        'limits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('slug', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('current_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 2. Create limit_versions table
    op.create_table(
        'limit_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('limit_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft', index=True),
        sa.Column('max_steps', sa.Integer, nullable=True),
        sa.Column('max_tool_calls', sa.Integer, nullable=True),
        sa.Column('max_wall_time_ms', sa.Integer, nullable=True),
        sa.Column('tool_timeout_ms', sa.Integer, nullable=True),
        sa.Column('max_retries', sa.Integer, nullable=True),
        sa.Column('extra_config', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('parent_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['limit_id'], ['limits.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_version_id'], ['limit_versions.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('limit_id', 'version', name='uix_limit_version'),
    )

    # 3. Add FK for current_version_id on limits
    op.create_foreign_key(
        'fk_limits_current_version',
        'limits', 'limit_versions',
        ['current_version_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_limits_current_version_id', 'limits', ['current_version_id'])

    # 4. Seed default limit from existing policy data
    op.execute("""
        INSERT INTO limits (slug, name, description)
        VALUES ('default', 'Default Limits', 'Standard execution limits')
    """)

    # 5. Create default limit version with values from default policy
    op.execute("""
        INSERT INTO limit_versions (limit_id, version, status, max_steps, max_tool_calls, max_wall_time_ms, tool_timeout_ms, max_retries)
        SELECT l.id, 1, 'active', 
            COALESCE(pv.max_steps, 20), 
            COALESCE(pv.max_tool_calls, 50), 
            COALESCE(pv.max_wall_time_ms, 300000), 
            COALESCE(pv.tool_timeout_ms, 30000), 
            COALESCE(pv.max_retries, 3)
        FROM limits l
        LEFT JOIN policies p ON p.slug = 'default'
        LEFT JOIN policy_versions pv ON pv.id = p.recommended_version_id
        WHERE l.slug = 'default'
    """)

    # 6. Set current_version_id on default limit
    op.execute("""
        UPDATE limits 
        SET current_version_id = (
            SELECT id FROM limit_versions 
            WHERE limit_id = limits.id AND version = 1
        )
        WHERE slug = 'default'
    """)


def downgrade() -> None:
    op.drop_constraint('fk_limits_current_version', 'limits', type_='foreignkey')
    op.drop_index('ix_limits_current_version_id', 'limits')
    op.drop_table('limit_versions')
    op.drop_table('limits')
