"""runtime helpers v2 schema bridge

Revision ID: 0035
Revises: 0034_plat_runtime_ovr
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0035'
down_revision = '0034_plat_runtime_ovr'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'system_llm_roles',
        sa.Column('extras', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.add_column(
        'system_llm_traces',
        sa.Column('caller_role', sa.String(length=32), nullable=True),
    )
    op.create_index(
        op.f('ix_system_llm_traces_caller_role'),
        'system_llm_traces',
        ['caller_role'],
        unique=False,
    )

    op.add_column(
        'dialogue_summaries',
        sa.Column(
            'summary_v2',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column('dialogue_summaries', 'summary_v2')

    op.drop_index(op.f('ix_system_llm_traces_caller_role'), table_name='system_llm_traces')
    op.drop_column('system_llm_traces', 'caller_role')

    op.drop_column('system_llm_roles', 'extras')
