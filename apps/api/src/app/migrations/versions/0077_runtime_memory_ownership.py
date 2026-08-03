"""Add generic durable-memory ownership and task success policy."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Legacy chat-scoped facts have no owner in the new durable-memory
    # contract. Remove them before replacing the scope constraint; otherwise
    # PostgreSQL rejects the new constraint while validating existing rows.
    op.execute(sa.text("DELETE FROM facts WHERE scope = 'chat'"))
    op.add_column("facts", sa.Column("owner_type", sa.String(length=32), nullable=True))
    op.add_column("facts", sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("facts", sa.Column("kind", sa.String(length=64), nullable=True))
    op.add_column("facts", sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.drop_index("ix_facts_user_scope", table_name="facts")
    op.drop_index("ix_facts_chat_observed", table_name="facts")
    # No data is carried from legacy ownership columns into the generic owner
    # contract. Existing user/tenant rows without generic ownership become
    # unreachable until an explicit backfill policy is introduced.
    op.drop_column("facts", "user_id")
    op.drop_column("facts", "chat_id")
    op.create_index(
        "ix_facts_owner_subject_active",
        "facts",
        ["owner_type", "owner_id", "subject"],
        postgresql_where=sa.text("superseded_by IS NULL"),
    )
    op.drop_constraint("ck_facts_scope", "facts", type_="check")
    op.create_check_constraint(
        "ck_facts_scope", "facts", "scope IN ('user', 'tenant', 'project')"
    )
    op.add_column(
        "runtime_plan_tasks",
        sa.Column("on_success", sa.String(length=32), nullable=False, server_default="continue"),
    )


def downgrade() -> None:
    op.drop_column("runtime_plan_tasks", "on_success")
    op.drop_constraint("ck_facts_scope", "facts", type_="check")
    op.create_check_constraint("ck_facts_scope", "facts", "scope IN ('chat', 'user', 'tenant')")
    op.drop_index("ix_facts_owner_subject_active", table_name="facts")
    op.drop_column("facts", "metadata")
    op.drop_column("facts", "kind")
    op.drop_column("facts", "owner_id")
    op.drop_column("facts", "owner_type")
    op.add_column("facts", sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("facts", sa.Column("chat_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_facts_user_scope", "facts", ["user_id", "scope"], postgresql_where=sa.text("superseded_by IS NULL"))
    op.create_index("ix_facts_chat_observed", "facts", ["chat_id", "observed_at"])
