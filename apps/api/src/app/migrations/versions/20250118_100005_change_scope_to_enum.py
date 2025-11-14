"""change scope column to enum type

Revision ID: 20250118_100005
Revises: 20250118_100004
Create Date: 2025-01-18 10:00:05.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20250118_100005'
down_revision = '20250118_100004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col['name'] for col in inspector.get_columns('ragdocuments')}

    if 'scope' not in columns:
        op.add_column('ragdocuments', sa.Column('scope', sa.String(length=20), nullable=True))
        op.execute("UPDATE ragdocuments SET scope = 'local' WHERE scope IS NULL")
        op.alter_column('ragdocuments', 'scope', nullable=False)
    else:
        op.execute("UPDATE ragdocuments SET scope = 'local' WHERE scope NOT IN ('local', 'global') OR scope IS NULL")

    enum_type = postgresql.ENUM('local', 'global', name='documentscope', create_type=True)
    enum_type.create(bind, checkfirst=True)

    op.alter_column(
        'ragdocuments',
        'scope',
        type_=enum_type,
        postgresql_using='scope::documentscope'
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col['name'] for col in inspector.get_columns('ragdocuments')}
    if 'scope' in columns:
        op.alter_column('ragdocuments', 'scope', type_=sa.String(20))
    enum_type = postgresql.ENUM('local', 'global', name='documentscope')
    enum_type.drop(bind, checkfirst=True)
