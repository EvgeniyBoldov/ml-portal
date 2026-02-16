"""Merge legacy branch head into main migration chain.

Revision ID: 0071_merge_main_heads
Revises: 0070_tool_schema_tracking, 0042_instance_type_rbac
Create Date: 2026-02-16
"""
from __future__ import annotations

from typing import Sequence, Union


revision: str = "0071_merge_main_heads"
down_revision: Union[str, Sequence[str], None] = (
    "0070_tool_schema_tracking",
    "0042_instance_type_rbac",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
