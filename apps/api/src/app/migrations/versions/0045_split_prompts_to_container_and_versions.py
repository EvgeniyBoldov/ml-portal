"""Split prompts table into prompts (container) and prompt_versions

Revision ID: 0045
Revises: 0044
Create Date: 2026-01-26 00:02:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0045'
down_revision = '0044'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Drop old prompts table (данные не нужны)
    op.execute("DROP TABLE IF EXISTS prompts CASCADE")
    
    # 2. Create new prompts table (container only)
    op.create_table(
        'prompts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slug', sa.String(255), nullable=False, unique=True, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('type', sa.String(50), nullable=False, server_default='prompt'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    )
    
    # 3. Create prompt_versions table
    op.create_table(
        'prompt_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('prompt_id', postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('template', sa.Text(), nullable=False),
        sa.Column('input_variables', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('generation_config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft', index=True),
        sa.Column('parent_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['prompt_id'], ['prompts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_version_id'], ['prompt_versions.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('prompt_id', 'version', name='uix_prompt_version')
    )
    
    # Индексы создаются автоматически SQLAlchemy (index=True в mapped_column)


def downgrade():
    # Drop new tables
    op.drop_table('prompt_versions')
    op.drop_table('prompts')
    
    # Recreate old prompts table structure
    op.create_table(
        'prompts',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('slug', sa.String(255), nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('template', sa.Text(), nullable=False),
        sa.Column('input_variables', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('generation_config', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('status', sa.String(20), nullable=False, server_default='draft', index=True),
        sa.Column('parent_version_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('type', sa.String(50), nullable=False, server_default='prompt'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['parent_version_id'], ['prompts.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('slug', 'version', name='uix_slug_version')
    )
