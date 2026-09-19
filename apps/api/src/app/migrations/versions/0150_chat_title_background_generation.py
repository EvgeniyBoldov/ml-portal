"""Track automatic versus manual chat titles.

Revision ID: 0150
Revises: 0149
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0150"
down_revision = "0149"
branch_labels = None
depends_on = None


def upgrade() -> None:
    uuid = postgresql.UUID(as_uuid=True)
    op.add_column(
        "chats",
        sa.Column("title_source", sa.String(length=16), nullable=False, server_default="default"),
    )
    op.execute("""
        UPDATE chats
        SET title_source = CASE
            WHEN lower(trim(coalesce(name, ''))) IN ('', 'new chat', 'новый чат') THEN 'default'
            ELSE 'manual'
        END
    """)
    op.create_check_constraint(
        "ck_chats_title_source",
        "chats",
        "title_source IN ('default', 'auto', 'manual')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_chats_title_source", "chats", type_="check")
    op.drop_column("chats", "title_source")
