"""Create tenants table"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003_create_tenants_table"
down_revision = "0002_create_user_tokens_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("embed_models", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("rerank_model", sa.String(length=255), nullable=True),
        sa.Column("ocr", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("layout", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_tenants_name", "tenants", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_tenants_name", table_name="tenants")
    op.drop_table("tenants")
