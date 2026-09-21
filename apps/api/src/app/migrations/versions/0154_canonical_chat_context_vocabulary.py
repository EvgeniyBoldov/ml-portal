"""Retire legacy chat-memory aliases and normalize inferred trust labels.

Revision ID: 0154
Revises: 0153
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0154"
down_revision = "0153"
branch_labels = None
depends_on = None


_CANONICAL_KINDS = (
    "'scope', 'goal', 'term_binding', 'artifact_ref', "
    "'open_loop', 'decision', 'recent_anchor', 'task_result_ref'"
)
_LEGACY_KINDS = "'open_question', 'chat_fact', 'summary'"


def upgrade() -> None:
    # Legacy rows have no target-compatible payload schema or provenance.
    # Keep them as expired archival records, but never permit them to enter a
    # snapshot or be reactivated under a compatibility alias.
    op.execute(
        """
        UPDATE chat_memory_items
        SET kind = CASE kind
            WHEN 'open_question' THEN 'open_loop'
            WHEN 'summary' THEN 'recent_anchor'
            WHEN 'chat_fact' THEN 'decision'
            ELSE kind
        END,
        status = CASE
            WHEN kind IN ('open_question', 'chat_fact', 'summary') THEN 'expired'
            ELSE status
        END
        WHERE kind IN ('open_question', 'chat_fact', 'summary')
        """
    )
    op.execute(
        """
        UPDATE chat_memory_items
        SET payload = jsonb_set(payload, '{trust_class}', '"model_inferred"'::jsonb, true)
        WHERE payload->>'trust_class' = 'compacted'
        """
    )
    op.drop_constraint("ck_chat_memory_items_kind", "chat_memory_items", type_="check")
    op.create_check_constraint(
        "ck_chat_memory_items_kind",
        "chat_memory_items",
        f"kind IN ({_CANONICAL_KINDS})",
    )
    # Prompt rows are operator-managed configuration.  Bootstrap backfill
    # intentionally fills only empty fields (SystemLLMRoleService), so a
    # schema migration must never rewrite them.


def downgrade() -> None:
    op.drop_constraint("ck_chat_memory_items_kind", "chat_memory_items", type_="check")
    op.create_check_constraint(
        "ck_chat_memory_items_kind",
        "chat_memory_items",
        f"kind IN ({_CANONICAL_KINDS}, {_LEGACY_KINDS})",
    )
