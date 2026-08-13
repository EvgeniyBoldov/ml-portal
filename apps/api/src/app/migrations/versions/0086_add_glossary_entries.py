"""Add the canonical terminology catalogue."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "glossary_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scope", sa.String(length=16), nullable=False, server_default="global"),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("canonical_term", sa.String(length=255), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.String()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("entity_type", sa.String(length=64), nullable=False, server_default="term"),
        sa.Column("entity_id", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("scope IN ('global', 'tenant', 'project')", name="ck_glossary_entries_scope"),
    )
    op.create_index("uq_glossary_entries_scope_term", "glossary_entries", ["scope", "tenant_id", "project_id", "canonical_term"], unique=True)
    op.create_index("ix_glossary_entries_entity", "glossary_entries", ["entity_type", "entity_id"])


def downgrade() -> None:
    op.drop_index("ix_glossary_entries_entity", table_name="glossary_entries")
    op.drop_index("uq_glossary_entries_scope_term", table_name="glossary_entries")
    op.drop_table("glossary_entries")
