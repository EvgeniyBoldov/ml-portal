"""Align legacy default prompts with TurnPreflight and PlannerStep contracts.

Revision ID: 0138
Revises: 0137
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0138"
down_revision = "0137"
branch_labels = None
depends_on = None


_LEGACY_PREFLIGHT = (
    "Используй только user request, mechanical lookup, continuation и recall context. "
    "Не отвечай пользователю, не создавай план, не выбирай агента и не выполняй инструменты. "
    "Верни synthesis, planner, recall или clarify."
)


def upgrade() -> None:
    # Only migrate the exact bootstrap values; admin-authored roles stay intact.
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET rules = :rules, output_requirements = :output_requirements, updated_at = now()
        WHERE role_type = 'turn_preflight' AND rules = :legacy
    """
    ).bindparams(
        rules=(
            "Используй только user request, mechanical lookup, continuation и recall context. "
            "Не создавай план, не выбирай агента и не выполняй tools. Для synthesis верни "
            "internal answer_draft для Synthesizer, основанный только на этом входе; это не прямое "
            "сообщение пользователю. После recall_context нельзя снова вернуть recall."
        ),
        output_requirements=(
            "Верни строгий TurnPreflightDecision: synthesis содержит synthesis_brief "
            "(SynthesisBrief плюс answer_draft), planner — полный TaskBrief, recall — MemoryRequest, "
            "clarify — вопрос. Ровно один route payload."
        ),
        legacy=_LEGACY_PREFLIGHT,
    ))
    op.execute(sa.text("""
        UPDATE system_llm_roles
        SET output_requirements = :output_requirements, updated_at = now()
        WHERE role_type = 'planner' AND output_requirements = :legacy
    """
    ).bindparams(
        output_requirements=(
            "Верни только строгий JSON PlannerStep по переданной JSON Schema: "
            "kind=tool_call для memory.search либо kind=proposal с IterationProposal."
        ),
        legacy="Верни только строгий JSON IterationProposal по переданной JSON Schema, без markdown и пояснений.",
    ))


def downgrade() -> None:
    # Prompt edits are intentionally not reversed: a later admin edit cannot
    # be distinguished from this migration safely.
    pass
