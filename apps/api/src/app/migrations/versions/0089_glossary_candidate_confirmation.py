"""Add candidate confirmation and evidence storage to the glossary.

Revision ID: 0089
Revises: 0088
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "glossary_entries",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
    )
    op.add_column(
        "glossary_entries",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="confirmed"),
    )
    op.add_column(
        "glossary_entries",
        sa.Column("support_count", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column("glossary_entries", sa.Column("first_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("glossary_entries", sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint("ck_glossary_entries_scope", "glossary_entries", type_="check")
    op.create_check_constraint(
        "ck_glossary_entries_scope",
        "glossary_entries",
        "scope IN ('global', 'user', 'tenant', 'project')",
    )
    op.create_check_constraint(
        "ck_glossary_entries_status",
        "glossary_entries",
        "status IN ('pending', 'confirmed', 'unconfirmed')",
    )
    op.create_index(
        "uq_glossary_entries_user_term",
        "glossary_entries",
        ["user_id", "canonical_term"],
        unique=True,
        postgresql_where=sa.text("scope = 'user'"),
    )
    op.create_table(
        "glossary_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("glossary_entries.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=128), nullable=False),
        sa.Column("source_label", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_glossary_observations_entry_id", "glossary_observations", ["entry_id"])
    op.create_index(
        "uq_glossary_observations_entry_source",
        "glossary_observations",
        ["entry_id", "source_type", "source_ref"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_glossary_observations_entry_source", table_name="glossary_observations")
    op.drop_index("ix_glossary_observations_entry_id", table_name="glossary_observations")
    op.drop_table("glossary_observations")
    op.drop_index("uq_glossary_entries_user_term", table_name="glossary_entries")
    op.drop_constraint("ck_glossary_entries_status", "glossary_entries", type_="check")
    op.drop_constraint("ck_glossary_entries_scope", "glossary_entries", type_="check")
    op.create_check_constraint(
        "ck_glossary_entries_scope",
        "glossary_entries",
        "scope IN ('global', 'tenant', 'project')",
    )
    op.drop_column("glossary_entries", "last_confirmed_at")
    op.drop_column("glossary_entries", "first_confirmed_at")
    op.drop_column("glossary_entries", "support_count")
    op.drop_column("glossary_entries", "status")
    op.drop_column("glossary_entries", "user_id")
