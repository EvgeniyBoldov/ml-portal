"""Add health check fields to tool_instances and models tables.

Revision ID: 0018
Revises: 0017
Create Date: 2026-05-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add health check fields to tool_instances
    op.add_column(
        "tool_instances",
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Number of consecutive health check failures",
        ),
    )
    op.add_column(
        "tool_instances",
        sa.Column(
            "next_check_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Next health check timestamp (for backoff scheduling)",
        ),
    )
    op.add_column(
        "tool_instances",
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Last health check error message",
        ),
    )
    
    # Add index for efficient candidate selection
    op.create_index(
        "ix_tool_instances_next_check_at",
        "tool_instances",
        ["next_check_at"],
    )

    # Add health check fields to models
    op.add_column(
        "models",
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            server_default="0",
            nullable=False,
            comment="Number of consecutive health check failures",
        ),
    )
    op.add_column(
        "models",
        sa.Column(
            "next_check_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Next health check timestamp (for backoff scheduling)",
        ),
    )
    op.add_column(
        "models",
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Last health check error message",
        ),
    )
    
    # Add index for efficient candidate selection
    op.create_index(
        "ix_models_next_check_at",
        "models",
        ["next_check_at"],
    )


def downgrade() -> None:
    # Remove indexes
    op.drop_index("ix_tool_instances_next_check_at", table_name="tool_instances")
    op.drop_index("ix_models_next_check_at", table_name="models")
    
    # Remove columns from tool_instances
    op.drop_column("tool_instances", "last_error")
    op.drop_column("tool_instances", "next_check_at")
    op.drop_column("tool_instances", "consecutive_failures")
    
    # Remove columns from models
    op.drop_column("models", "last_error")
    op.drop_column("models", "next_check_at")
    op.drop_column("models", "consecutive_failures")
