"""Make glossary observations source-visible definition claims."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0126"
down_revision = "0125"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("glossary_observations", sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("glossary_observations", sa.Column("visibility_tenant_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("glossary_observations", sa.Column("definition", sa.Text(), nullable=True))
    op.add_column("glossary_observations", sa.Column("aliases", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"))
    op.add_column("glossary_observations", sa.Column("state", sa.String(length=16), nullable=False, server_default="active"))
    op.create_foreign_key("fk_glossary_observations_document", "glossary_observations", "ragdocuments", ["document_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_glossary_observations_visibility_tenant", "glossary_observations", "tenants", ["visibility_tenant_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_glossary_observations_document", "glossary_observations", ["document_id"])
    op.create_index("ix_glossary_observations_visibility_tenant", "glossary_observations", ["visibility_tenant_id"])
    op.execute(sa.text("""
        UPDATE glossary_observations observation
        SET definition = entry.description, aliases = entry.aliases
        FROM glossary_entries entry
        WHERE entry.id = observation.entry_id
    """))
    op.execute(sa.text("""
        UPDATE glossary_entries entry
        SET is_active = false, status = 'unconfirmed', updated_at = now()
        WHERE entry.scope = 'tenant'
          AND EXISTS (
              SELECT 1 FROM glossary_observations observation
              WHERE observation.entry_id = entry.id AND observation.source_type = 'document'
          )
    """))


def downgrade() -> None:
    op.drop_index("ix_glossary_observations_visibility_tenant", table_name="glossary_observations")
    op.drop_index("ix_glossary_observations_document", table_name="glossary_observations")
    op.drop_constraint("fk_glossary_observations_visibility_tenant", "glossary_observations", type_="foreignkey")
    op.drop_constraint("fk_glossary_observations_document", "glossary_observations", type_="foreignkey")
    op.drop_column("glossary_observations", "state")
    op.drop_column("glossary_observations", "aliases")
    op.drop_column("glossary_observations", "definition")
    op.drop_column("glossary_observations", "visibility_tenant_id")
    op.drop_column("glossary_observations", "document_id")
