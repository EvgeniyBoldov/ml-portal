"""Add confirmed fact lifecycle, observations, and the project catalogue.

Schema-only migration.  Existing fact rows deliberately remain untouched:
without generic ownership they are legacy state and cannot be promoted into
the confirmed-memory read path automatically.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint("check_system_llm_role_type", "system_llm_roles", "role_type IN ('triage', 'planner', 'summary', 'memory', 'synthesizer', 'fact_extractor', 'summary_compactor', 'fact_compactor')")
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.String()), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("uq_projects_key", "projects", ["key"], unique=True)

    op.add_column("facts", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_facts_project_id", "facts", "projects", ["project_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_facts_project_id", "facts", ["project_id"])
    op.add_column("facts", sa.Column("normalized_value", sa.String(length=500), nullable=True))
    op.add_column("facts", sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"))
    op.add_column("facts", sa.Column("support_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("facts", sa.Column("first_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("facts", sa.Column("last_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("facts", sa.Column("revision", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_facts_owner_subject_status", "facts", ["owner_type", "owner_id", "subject", "status"])
    op.drop_constraint("ck_facts_scope", "facts", type_="check")
    op.create_check_constraint("ck_facts_scope", "facts", "scope IN ('user', 'tenant', 'project')")
    op.drop_constraint("ck_facts_source", "facts", type_="check")
    # Keep the old value legal so a schema migration never rewrites user data.
    # Runtime extraction no longer emits it and confirmed reads exclude legacy rows.
    op.create_check_constraint("ck_facts_source", "facts", "source IN ('user_utterance', 'tool_result', 'manual', 'system', 'agent_result')")
    op.create_check_constraint("ck_facts_status", "facts", "status IN ('pending', 'confirmed', 'unconfirmed', 'deleted')")

    op.create_table(
        "fact_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_ref", sa.String(length=255), nullable=False),
        sa.Column("source_label", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_fact_observations_fact_id", "fact_observations", ["fact_id"])
    op.create_index("uq_fact_observations_fact_source", "fact_observations", ["fact_id", "source_type", "source_ref"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_fact_observations_fact_source", table_name="fact_observations")
    op.drop_index("ix_fact_observations_fact_id", table_name="fact_observations")
    op.drop_table("fact_observations")
    op.drop_constraint("ck_facts_status", "facts", type_="check")
    op.drop_constraint("ck_facts_source", "facts", type_="check")
    op.create_check_constraint("ck_facts_source", "facts", "source IN ('user_utterance', 'agent_result', 'system')")
    op.drop_constraint("ck_facts_scope", "facts", type_="check")
    op.create_check_constraint("ck_facts_scope", "facts", "scope IN ('user', 'tenant')")
    op.drop_index("ix_facts_owner_subject_status", table_name="facts")
    op.drop_column("facts", "revision")
    op.drop_column("facts", "last_confirmed_at")
    op.drop_column("facts", "first_confirmed_at")
    op.drop_column("facts", "support_count")
    op.drop_column("facts", "status")
    op.drop_column("facts", "normalized_value")
    op.drop_index("ix_facts_project_id", table_name="facts")
    op.drop_constraint("fk_facts_project_id", "facts", type_="foreignkey")
    op.drop_column("facts", "project_id")
    op.drop_index("uq_projects_key", table_name="projects")
    op.drop_table("projects")
    op.drop_constraint("check_system_llm_role_type", "system_llm_roles", type_="check")
    op.create_check_constraint("check_system_llm_role_type", "system_llm_roles", "role_type IN ('triage', 'planner', 'summary', 'memory', 'synthesizer', 'fact_extractor', 'summary_compactor')")
