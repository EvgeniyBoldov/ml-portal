"""
Drop baselines/baseline_versions tables.
Remove baseline_id from agents.
Add limit_id to agents.

Revision ID: 0063
Revises: 0062
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0063'
down_revision = '0062'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop baseline_id FK from agents
    op.drop_constraint('agents_baseline_id_fkey', 'agents', type_='foreignkey')
    op.drop_index('ix_agents_baseline_id', 'agents')
    op.drop_column('agents', 'baseline_id')

    # 2. Add limit_id to agents
    op.add_column('agents', sa.Column(
        'limit_id',
        postgresql.UUID(as_uuid=True),
        nullable=True,
    ))
    op.create_foreign_key(
        'agents_limit_id_fkey',
        'agents', 'limits',
        ['limit_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_agents_limit_id', 'agents', ['limit_id'])

    # 3. Set default limit for existing agents
    op.execute("""
        UPDATE agents 
        SET limit_id = (SELECT id FROM limits WHERE slug = 'default')
        WHERE limit_id IS NULL
    """)

    # 4. Drop baseline_versions table first (has FK to baselines)
    op.drop_table('baseline_versions')

    # 5. Drop baselines table
    op.drop_table('baselines')


def downgrade() -> None:
    # 1. Recreate baselines table
    op.create_table(
        'baselines',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slug', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('scope', sa.String(20), nullable=False, server_default='default', index=True),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('recommended_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    # 2. Recreate baseline_versions table
    op.create_table(
        'baseline_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('baseline_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('template', sa.Text, nullable=False),
        sa.Column('version', sa.Integer, nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft', index=True),
        sa.Column('parent_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['baseline_id'], ['baselines.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_version_id'], ['baseline_versions.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('baseline_id', 'version', name='uix_baseline_version'),
    )

    # 3. Add baseline_id back to agents
    op.add_column('agents', sa.Column(
        'baseline_id',
        postgresql.UUID(as_uuid=True),
        nullable=True,
    ))
    op.create_foreign_key(
        'agents_baseline_id_fkey',
        'agents', 'baselines',
        ['baseline_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_agents_baseline_id', 'agents', ['baseline_id'])

    # 4. Drop limit_id from agents
    op.drop_constraint('agents_limit_id_fkey', 'agents', type_='foreignkey')
    op.drop_index('ix_agents_limit_id', 'agents')
    op.drop_column('agents', 'limit_id')
