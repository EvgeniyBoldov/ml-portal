"""Seed default model alias for FACT_EXTRACTOR / SUMMARY_COMPACTOR / SYNTHESIZER.

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-19

When migrations 0008 and 0010 seeded the new roles they left the `model`
column NULL. The StructuredLLMCall helper falls back to the literal
string "unknown" in that case, which the upstream LLM provider
(correctly) rejects with HTTP 404 'model_not_found'.

This migration sets `model = 'llm.llama4.scout'` on the three affected
active rows, matching the default used by PLANNER / SUMMARY / MEMORY. It
only touches rows whose `model` is currently NULL so manual overrides
set via the admin UI are preserved.

Down-migration simply clears the model back to NULL.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


TARGET_ROLES = ("fact_extractor", "summary_compactor", "synthesizer")
DEFAULT_MODEL = "llm.llama4.scout"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE system_llm_roles SET model = :m "
            "WHERE role_type = ANY(:roles) "
            "  AND model IS NULL "
            "  AND COALESCE(is_active, true) = true"
        ),
        {"m": DEFAULT_MODEL, "roles": list(TARGET_ROLES)},
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE system_llm_roles SET model = NULL "
            "WHERE role_type = ANY(:roles) "
            "  AND model = :m "
            "  AND COALESCE(is_active, true) = true"
        ),
        {"m": DEFAULT_MODEL, "roles": list(TARGET_ROLES)},
    )
