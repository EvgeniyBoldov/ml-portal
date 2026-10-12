"""Classify agents for orchestration or direct shadow invocation."""
from alembic import op
import sqlalchemy as sa

revision = "0185"
down_revision = "0184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("agent_type", sa.String(20), nullable=True, server_default="regular"))
    op.execute("UPDATE agents SET agent_type = 'regular' WHERE agent_type IS NULL")
    op.alter_column("agents", "agent_type", nullable=False)
    op.create_check_constraint("ck_agents_agent_type", "agents", "agent_type IN ('regular', 'shadow')")


def downgrade() -> None:
    op.drop_constraint("ck_agents_agent_type", "agents", type_="check")
    op.drop_column("agents", "agent_type")
