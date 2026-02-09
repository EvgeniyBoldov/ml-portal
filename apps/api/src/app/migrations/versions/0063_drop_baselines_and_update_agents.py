"""Drop baselines/baseline_versions tables, remove baseline_prompt_id from agents.

This is a transitional migration. Agent v2 schema (agent_versions, etc.) is in 0064.

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
    conn = op.get_bind()

    # 1. Drop baseline_prompt_id from agents (added in migration 0043)
    conn.execute(sa.text(
        "ALTER TABLE agents DROP CONSTRAINT IF EXISTS fk_agents_baseline_prompt_id"
    ))
    conn.execute(sa.text(
        "DROP INDEX IF EXISTS ix_agents_baseline_prompt_id"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agents DROP COLUMN IF EXISTS baseline_prompt_id"
    ))

    # 2. Drop baselines + baseline_versions (CASCADE handles cross-FKs)
    conn.execute(sa.text("DROP TABLE IF EXISTS baseline_versions CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS baselines CASCADE"))


def downgrade() -> None:
    # Recreate baselines table
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

    # Recreate baseline_versions table
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

    # Add baseline_prompt_id back to agents
    op.add_column('agents', sa.Column(
        'baseline_prompt_id',
        postgresql.UUID(as_uuid=True),
        nullable=True,
    ))
    op.create_foreign_key(
        'fk_agents_baseline_prompt_id',
        'agents', 'prompts',
        ['baseline_prompt_id'], ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_agents_baseline_prompt_id', 'agents', ['baseline_prompt_id'])
