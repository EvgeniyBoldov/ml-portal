"""Typed memory scope catalog and document/claim applicability bindings.

Revision ID: 0164
Revises: 0163
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0164"
down_revision = "0163"
branch_labels = None
depends_on = None


def upgrade() -> None:
    key = postgresql.UUID(as_uuid=True)
    scope_type = postgresql.ENUM("product", "project", "team", name="memoryscopetype", create_type=False)
    scope_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "memory_scopes",
        sa.Column("id", key, primary_key=True),
        sa.Column("scope_type", scope_type, nullable=False),
        sa.Column("key", sa.String(180), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.String()), nullable=False, server_default=sa.text("'{}'::varchar[]")),
        sa.Column("is_all", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("project_id", key, sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("scope_type", "key", name="uq_memory_scopes_type_key"),
        sa.UniqueConstraint("project_id", name="uq_memory_scopes_project_id"),
        sa.CheckConstraint("key LIKE scope_type::text || '.%' AND ((is_all AND key = scope_type::text || '.all') OR (NOT is_all AND key <> scope_type::text || '.all'))", name="ck_memory_scopes_all_key"),
        sa.CheckConstraint("project_id IS NULL OR (scope_type = 'project' AND NOT is_all)", name="ck_memory_scopes_project_type"),
    )
    op.create_index("uq_memory_scopes_all_type", "memory_scopes", ["scope_type"], unique=True, postgresql_where=sa.text("is_all"))

    op.create_table(
        "document_memory_scopes",
        sa.Column("document_id", key, sa.ForeignKey("ragdocuments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("scope_id", key, sa.ForeignKey("memory_scopes.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("method", sa.String(32), nullable=False, server_default="explicit"),
    )
    op.create_table(
        "memory_candidate_scopes",
        sa.Column("id", key, primary_key=True),
        sa.Column("candidate_id", key, sa.ForeignKey("memory_extraction_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_id", key, sa.ForeignKey("memory_scopes.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="suggested"),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.UniqueConstraint("candidate_id", "scope_id", "role", name="uq_memory_candidate_scopes_binding"),
        sa.CheckConstraint("role IN ('applies_to', 'mentions')", name="ck_memory_candidate_scopes_role"),
        sa.CheckConstraint("status IN ('suggested', 'confirmed', 'rejected')", name="ck_memory_candidate_scopes_status"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_memory_candidate_scopes_confidence"),
    )
    op.create_index("ix_memory_candidate_scopes_candidate_id", "memory_candidate_scopes", ["candidate_id"])
    op.create_index("ix_memory_candidate_scopes_scope_id", "memory_candidate_scopes", ["scope_id"])
    op.create_table(
        "memory_claim_scopes",
        sa.Column("claim_id", key, sa.ForeignKey("memory_claims.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("scope_id", key, sa.ForeignKey("memory_scopes.id", ondelete="RESTRICT"), primary_key=True),
    )
    op.drop_constraint("ck_memory_candidate_scope", "memory_extraction_candidates", type_="check")
    op.create_check_constraint("ck_memory_candidate_scope", "memory_extraction_candidates",
                               "scope_candidate IS NULL OR scope_candidate IN ('global', 'project', 'multi_project', 'scoped', 'unknown')")

    connection = op.get_bind()
    for scope_type, name in (("product", "Все продукты"), ("project", "Все проекты"), ("team", "Все подразделения")):
        connection.execute(sa.text("""
            INSERT INTO memory_scopes (id, scope_type, key, name, is_all)
            VALUES (:id, :scope_type, :key, :name, true)
        """), {"id": uuid.uuid4(), "scope_type": scope_type, "key": f"{scope_type}.all", "name": name})

    # Keep existing project identity stable by linking each catalog row to
    # its project rather than trying to replace project IDs in legacy reads.
    projects = connection.execute(sa.text("SELECT id, key, name, aliases FROM projects")).mappings().all()
    for project in projects:
        connection.execute(sa.text("""
            INSERT INTO memory_scopes (id, scope_type, key, name, aliases, project_id)
            VALUES (:id, 'project', :key, :name, :aliases, :project_id)
        """), {"id": uuid.uuid4(), "key": f"project.{project['key']}", "name": project["name"],
               "aliases": project["aliases"] or [], "project_id": project["id"]})
    connection.execute(sa.text("""
        INSERT INTO memory_claim_scopes (claim_id, scope_id)
        SELECT c.id, s.id FROM memory_claims c
        JOIN memory_scopes s ON s.project_id = c.project_id
        WHERE c.project_id IS NOT NULL
    """))
    connection.execute(sa.text("""
        INSERT INTO document_memory_scopes (document_id, scope_id, method)
        SELECT source.source_id, scope.id, 'migration'
        FROM sources source
        CROSS JOIN LATERAL jsonb_array_elements_text(
            CASE WHEN jsonb_typeof(source.meta->'memory'->'project_keys') = 'array'
                 THEN source.meta->'memory'->'project_keys' ELSE '[]'::jsonb END
        ) AS project_key(value)
        JOIN memory_scopes scope ON scope.key = 'project.' || lower(trim(project_key.value))
        JOIN ragdocuments document ON document.id = source.source_id
        ON CONFLICT (document_id, scope_id) DO NOTHING
    """))
    connection.execute(sa.text("""
        INSERT INTO memory_candidate_scopes (id, candidate_id, scope_id, role, status, method, confidence, rationale)
        SELECT b.id, b.candidate_id, s.id, b.role, b.status, b.method, b.confidence, b.rationale
        FROM memory_candidate_project_bindings b
        JOIN memory_scopes s ON s.project_id = b.project_id
    """))


def downgrade() -> None:
    op.drop_constraint("ck_memory_candidate_scope", "memory_extraction_candidates", type_="check")
    op.create_check_constraint("ck_memory_candidate_scope", "memory_extraction_candidates",
                               "scope_candidate IS NULL OR scope_candidate IN ('global', 'project', 'multi_project', 'unknown')")
    op.drop_table("memory_claim_scopes")
    op.drop_index("ix_memory_candidate_scopes_scope_id", table_name="memory_candidate_scopes")
    op.drop_index("ix_memory_candidate_scopes_candidate_id", table_name="memory_candidate_scopes")
    op.drop_table("memory_candidate_scopes")
    op.drop_table("document_memory_scopes")
    op.drop_index("uq_memory_scopes_all_type", table_name="memory_scopes")
    op.drop_table("memory_scopes")
    postgresql.ENUM("product", "project", "team", name="memoryscopetype").drop(op.get_bind(), checkfirst=True)
