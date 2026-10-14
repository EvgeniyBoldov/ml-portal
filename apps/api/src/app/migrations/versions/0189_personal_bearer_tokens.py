"""Replace legacy API keys with personal Bearer tokens.

Revision ID: 0189
Revises: 0188
"""
from alembic import op
import sqlalchemy as sa

revision = "0189"
down_revision = "0188"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Credential replacement is intentional: no legacy token adapter or fallback.
    op.execute(sa.text("DELETE FROM api_tokens"))
    op.drop_table("api_keys")
    op.drop_column("api_tokens", "scopes")
    op.alter_column("api_tokens", "token_prefix", existing_type=sa.String(10), type_=sa.String(20))


def downgrade() -> None:
    raise RuntimeError("Personal Bearer credential replacement is irreversible; revoked secrets cannot be restored")
