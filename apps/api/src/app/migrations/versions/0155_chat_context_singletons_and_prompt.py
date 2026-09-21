"""Enforce singleton context rows and safely refresh the shipped role prompt.

Revision ID: 0155
Revises: 0154
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0155"
down_revision = "0154"
branch_labels = None
depends_on = None


_SINGLETON_KINDS = "'scope', 'goal', 'recent_anchor'"
_OLD_RULES = "Используй только snapshot, recent_dialogue, outcome и valid_source_ids. Верни максимум один topic/goal/recent_anchor и до трёх explicit decisions. Нельзя создавать scope, artifact_ref, term_binding, open_loop или task_result_ref: ими владеет детерминированный runtime. Каждая операция должна ссылаться только на существующие valid_source_ids. Не выдумывай файлы, проекты, действия, факты, статусы внешних систем или идентификаторы. При неоднозначности не делай операцию."
_NEW_RULES = "Используй только snapshot, recent_dialogue, outcome и valid_source_ids. Верни максимум один inferred topic (scope без project_keys/entity_refs), goal/recent_anchor и до трёх explicit decisions. Нельзя создавать project/entity scope, artifact_ref, term_binding, open_loop или task_result_ref: ими владеет детерминированный runtime. Каждая операция должна ссылаться только на существующие valid_source_ids. Не выдумывай файлы, проекты, действия, факты, статусы внешних систем или идентификаторы. При неоднозначности не делай операцию."
_OLD_OUTPUT = "Верни только JSON с operations[]. operation содержит action(add|update), kind(goal|decision|recent_anchor), item_key, payload и source_ids. payload должен быть компактным, не более 600 символов текста."
_NEW_OUTPUT = "Верни только JSON с operations[]. operation содержит action(add|update), kind(scope|goal|decision|recent_anchor), item_key, payload и source_ids. Для kind=scope разрешён только inferred topic без project_keys/entity_refs. payload должен быть компактным, не более 600 символов текста."


def upgrade() -> None:
    # Historical duplicate singleton rows are retired deterministically before
    # the partial unique indexes make the invariant database-enforced.
    op.execute(
        """
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY chat_id, sandbox_branch_id, kind
                ORDER BY updated_at DESC, id DESC
            ) AS rank
            FROM chat_memory_items
            WHERE status = 'active' AND kind IN ('scope', 'goal', 'recent_anchor')
        )
        UPDATE chat_memory_items AS item
        SET status = 'superseded'
        FROM ranked
        WHERE item.id = ranked.id AND ranked.rank > 1
        """
    )
    op.create_index(
        "uq_chat_memory_active_root_singleton", "chat_memory_items", ["chat_id", "kind"], unique=True,
        postgresql_where=sa.text(f"status = 'active' AND sandbox_branch_id IS NULL AND kind IN ({_SINGLETON_KINDS})"),
    )
    op.create_index(
        "uq_chat_memory_active_branch_singleton", "chat_memory_items", ["chat_id", "sandbox_branch_id", "kind"], unique=True,
        postgresql_where=sa.text(f"status = 'active' AND sandbox_branch_id IS NOT NULL AND kind IN ({_SINGLETON_KINDS})"),
    )
    # Only update the exact old shipped default. Operator-authored prompts
    # remain configuration, not migration-owned data.
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = :new_rules, output_requirements = :new_output
        WHERE role_type = 'chat_context_compactor'
          AND rules = :old_rules
          AND output_requirements = :old_output
    """).bindparams(
        new_rules=_NEW_RULES, new_output=_NEW_OUTPUT,
        old_rules=_OLD_RULES, old_output=_OLD_OUTPUT,
    ))


def downgrade() -> None:
    op.drop_index("uq_chat_memory_active_branch_singleton", table_name="chat_memory_items")
    op.drop_index("uq_chat_memory_active_root_singleton", table_name="chat_memory_items")
