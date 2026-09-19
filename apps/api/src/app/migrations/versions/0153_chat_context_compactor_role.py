"""Add the bounded chat-context compactor system role.

Revision ID: 0153
Revises: 0152
"""
from __future__ import annotations

from alembic import op


revision = "0153"
down_revision = "0152"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint(
        "check_system_llm_role_type", "system_llm_roles",
        "role_type IN ('planner', 'memory', 'turn_preflight', 'synthesizer', 'fact_extractor', 'fact_compactor', 'document_memory_extractor', 'memory_evaluator', 'chat_context_compactor')",
    )


def downgrade() -> None:
    # This role type was introduced by this revision; remove its system
    # configuration before restoring the older database constraint.
    op.execute("DELETE FROM system_llm_roles WHERE role_type = 'chat_context_compactor'")
    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint(
        "check_system_llm_role_type", "system_llm_roles",
        "role_type IN ('planner', 'memory', 'turn_preflight', 'synthesizer', 'fact_extractor', 'fact_compactor', 'document_memory_extractor', 'memory_evaluator')",
    )
