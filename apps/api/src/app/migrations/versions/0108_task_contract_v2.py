"""Introduce versioned agent task contracts and cut over runtime plans to v2.

Revision ID: 0108
Revises: 0107
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_versions", sa.Column("task_contracts", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("agent_versions", sa.Column("supports_dynamic_contracts", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.add_column("runtime_plans", sa.Column("contract_version", sa.Integer(), nullable=False, server_default=sa.text("2")))
    op.add_column("runtime_plan_tasks", sa.Column("compiled_contract", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))

    # No v1 execution adapter: a resumed pre-v2 plan could otherwise replay
    # operations under semantics different from the persisted declaration.
    op.execute(
        "UPDATE runtime_plans "
        "SET status = 'failed', last_failure = jsonb_build_object(" 
        "'code', 'contract_version_unsupported', "
        "'message', 'The runtime task contract was upgraded to v2; restart the request.'" 
        ") "
        "WHERE status IN ('draft', 'active', 'waiting_input')"
    )


def downgrade() -> None:
    op.drop_column("runtime_plan_tasks", "compiled_contract")
    op.drop_column("runtime_plans", "contract_version")
    op.drop_column("agent_versions", "supports_dynamic_contracts")
    op.drop_column("agent_versions", "task_contracts")
