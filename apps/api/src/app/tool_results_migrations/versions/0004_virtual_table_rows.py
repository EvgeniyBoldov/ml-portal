"""Stable row identity, independent of source record IDs and pagination ordinals."""
from alembic import op
import sqlalchemy as sa

revision = 'tool_results_0004'
down_revision = 'tool_results_0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('runtime_tool_result_rows', sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False))
    op.create_unique_constraint('uq_tool_result_row_id', 'runtime_tool_result_rows', ['id'])


def downgrade() -> None:
    op.drop_constraint('uq_tool_result_row_id', 'runtime_tool_result_rows', type_='unique')
    op.drop_column('runtime_tool_result_rows', 'id')
