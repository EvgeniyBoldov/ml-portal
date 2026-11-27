"""Persist verified external assignment identity links."""
from alembic import op
import sqlalchemy as sa

revision = "0218"
down_revision = "0217"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "external_assignment_identities",
        sa.Column("source", sa.String(100), primary_key=True),
        sa.Column("external_id", sa.String(100), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("source", "user_id", name="uq_assignment_source_user"),
    )


def downgrade() -> None:
    op.drop_table("external_assignment_identities")
