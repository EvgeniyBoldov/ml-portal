"""Persist effective scope context on plans and task handoffs.

Revision ID: 0178
Revises: 0177
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0178"
down_revision = "0177"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runtime_plans", sa.Column("scope_context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("runtime_plans", sa.Column("memory_context", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("runtime_plan_tasks", sa.Column("scope_context", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))


def downgrade() -> None:
    op.execute(sa.text("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM runtime_plans WHERE scope_context <> '{}'::jsonb OR memory_context <> '[]'::jsonb)
             OR EXISTS (SELECT 1 FROM runtime_plan_tasks WHERE scope_context <> '{}'::jsonb)
          THEN RAISE EXCEPTION '0178 downgrade would discard persisted scope or memory context';
          END IF;
        END $$;
    """))
    op.drop_column("runtime_plan_tasks", "scope_context")
    op.drop_column("runtime_plans", "memory_context")
    op.drop_column("runtime_plans", "scope_context")
