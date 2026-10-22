"""Make chat turn idempotency atomic within its chat and user.

Revision ID: 0202
Revises: 0201
"""
from alembic import op
import sqlalchemy as sa

revision = "0202"
down_revision = "0201"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the newest legacy turn for each scoped key. Older duplicates cannot
    # safely be replayed and are made non-idempotent before adding the index.
    op.execute(sa.text("""
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY chat_id, user_id, idempotency_key
                ORDER BY started_at DESC, id DESC
            ) AS position
            FROM chat_turns
            WHERE idempotency_key IS NOT NULL
        )
        UPDATE chat_turns AS turns
        SET idempotency_key = NULL
        FROM ranked
        WHERE turns.id = ranked.id AND ranked.position > 1
    """))
    op.create_unique_constraint(
        "uq_chat_turns_chat_user_idempotency",
        "chat_turns",
        ["chat_id", "user_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_chat_turns_chat_user_idempotency", "chat_turns", type_="unique")
