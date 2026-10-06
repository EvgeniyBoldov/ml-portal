"""Explicit user/tenant scope preferences and execution-first turn routing.

Revision ID: 0182
Revises: 0181
"""
from alembic import op
import sqlalchemy as sa

from app.services.turn_preflight_prompt import TURN_PREFLIGHT_PROMPT_V2

revision = "0182"
down_revision = "0181"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("users", "tenants"):
        op.add_column(table, sa.Column("memory_scope_keys", sa.ARRAY(sa.String()), nullable=True, server_default="{}"))
        op.execute(sa.text(f"UPDATE {table} SET memory_scope_keys = '{{}}' WHERE memory_scope_keys IS NULL"))
        op.alter_column(table, "memory_scope_keys", nullable=False)
    # Keep operator model, temperature and limits; replace only the routing policy.
    op.execute(sa.text("""UPDATE system_llm_roles SET
        identity = :identity, mission = :mission, rules = :rules,
        safety = :safety, output_requirements = :output_requirements,
        examples = '[]'::jsonb, updated_at = now()
        WHERE role_type = 'turn_preflight' AND is_active IS TRUE
    """).bindparams(**TURN_PREFLIGHT_PROMPT_V2))


def downgrade() -> None:
    for table in ("tenants", "users"):
        op.drop_column(table, "memory_scope_keys")
    # Prompt edits are operator configuration and are not rolled back.
