# app/migrations/versions/20250102_120000_add_user_tenants_m2m.py
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20250102_120000"
down_revision = "20250910_175628_initial"
branch_labels = None
depends_on = None


def upgrade():
    # Create tenants table
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.String(1000), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    
    # Create user_tenants table
    op.create_table(
        'user_tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'tenant_id', name='uq_user_tenants_user_tenant'),
    )
    
    # Create indexes
    op.create_index('ix_user_tenants_user_id', 'user_tenants', ['user_id'])
    op.create_index('ix_user_tenants_tenant_id', 'user_tenants', ['tenant_id'])
    op.create_index('idx_users_created_id', 'users', ['created_at', 'id'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_users_created_id', 'users')
    op.drop_index('ix_user_tenants_tenant_id', 'user_tenants')
    op.drop_index('ix_user_tenants_user_id', 'user_tenants')
    
    # Drop tables
    op.drop_table('user_tenants')
    op.drop_table('tenants')
