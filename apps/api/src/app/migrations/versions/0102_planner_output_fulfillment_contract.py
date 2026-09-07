"""Clarify planner output fulfillment provenance.

Revision ID: 0102
Revises: 0101
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None


_RULE = (
    " Для каждого expected_output явно выбери fulfillment. fulfillment=artifact подтверждается только "
    "runtime-созданным файлом. Для fulfillment=verified_receipt обязательно укажи непустой "
    "receipt_operations с допустимыми canonical operation names; receipt другой операции не засчитывается."
)


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            """
            UPDATE system_llm_roles
            SET rules = rtrim(rules) || :rule
            WHERE role_type = 'planner'
              AND is_active = true
              AND rules NOT LIKE '%receipt_operations%'
            """
        ),
        {"rule": _RULE},
    )


def downgrade() -> None:
    raise RuntimeError("strict planner fulfillment contract is irreversible")
