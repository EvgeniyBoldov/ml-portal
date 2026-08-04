"""Add branch-local sandbox fact overlays and restrict new fact scopes.

Revision ID: 0078
Revises: 0077
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sandbox_branches",
        sa.Column(
            "fact_overrides_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    # This migration intentionally does not rewrite user data. Deployments
    # with legacy project facts must remediate those rows explicitly before
    # tightening the database constraint.
    op.drop_constraint("ck_facts_scope", "facts", type_="check")
    op.create_check_constraint(
        "ck_facts_scope",
        "facts",
        "scope IN ('user', 'tenant')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_facts_scope", "facts", type_="check")
    op.create_check_constraint(
        "ck_facts_scope",
        "facts",
        "scope IN ('user', 'tenant', 'project')",
    )
    op.drop_column("sandbox_branches", "fact_overrides_json")
