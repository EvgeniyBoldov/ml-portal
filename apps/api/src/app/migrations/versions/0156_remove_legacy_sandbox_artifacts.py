"""Remove obsolete sandbox artifact JSON columns.

Revision ID: 0156
Revises: 0155
"""
from __future__ import annotations

from alembic import op


revision = "0156"
down_revision = "0155"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("sandbox_branches", "facts_artifact_json")
    op.drop_column("sandbox_branches", "summary_artifact_json")


def downgrade() -> None:
    # The removed JSON blobs had no active writer in the canonical runtime.
    # Recreate empty columns only for schema rollback compatibility.
    import sqlalchemy as sa
    from sqlalchemy.dialects import postgresql

    op.add_column("sandbox_branches", sa.Column(
        "facts_artifact_json", postgresql.JSONB(astext_type=sa.Text()),
        nullable=False, server_default=sa.text("'[]'::jsonb"),
    ))
    op.add_column("sandbox_branches", sa.Column(
        "summary_artifact_json", postgresql.JSONB(astext_type=sa.Text()),
        nullable=False, server_default=sa.text("'{}'::jsonb"),
    ))
