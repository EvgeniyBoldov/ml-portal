"""Drop semantic_profile / policy_hints JSONB layers from tool_releases and collection_versions.

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-20

Rationale
---------
Both tool releases and collection versions used to carry a structured
"semantic layer" (summary / when_to_use / limitations / examples /
dos / donts / guardrails / sensitive_inputs / entity_types / ...).

With the MVP semantic layer removed we treat:
- MCP-discovered schema + description as the single source of truth
  for tool ops;
- Collection.description (+ entity_type, fields) as the single source
  of truth for collections.

Down migration restores the columns as empty JSONB blobs (data is
permanently lost — this layer was descriptive metadata and there is
nothing we need to preserve).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("tool_releases", "semantic_profile")
    op.drop_column("tool_releases", "policy_hints")
    op.drop_column("collection_versions", "semantic_profile")
    op.drop_column("collection_versions", "policy_hints")


def downgrade() -> None:
    op.add_column(
        "collection_versions",
        sa.Column(
            "policy_hints",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "collection_versions",
        sa.Column(
            "semantic_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "tool_releases",
        sa.Column(
            "policy_hints",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "tool_releases",
        sa.Column(
            "semantic_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
