"""Add a no-op revision after 0174 for release recovery.

Revision ID: 0175
Revises: 0174
"""
from __future__ import annotations


revision = "0175"
down_revision = "0174"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
