"""RBAC v2: rbac_policies, rbac_rules, platform_settings tables.

- rbac_policies: named sets of RBAC rules
- rbac_rules: granular resource-level access rules (level + resource_type + resource_id → effect)
- platform_settings: singleton table for global defaults (policy, limit, rbac_policy)

Revision ID: 0066
Revises: 0065
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0066'
down_revision = '0065'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    def _table_exists(table: str) -> bool:
        return conn.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            f"WHERE table_name = '{table}'"
        )).fetchone() is not None

    # ═══════════════════════════════════════════════════════════════════
    # 1. RBAC_POLICIES
    # ═══════════════════════════════════════════════════════════════════
    if not _table_exists('rbac_policies'):
        conn.execute(sa.text("""
            CREATE TABLE rbac_policies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                slug VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT uq_rbac_policy_slug UNIQUE (slug)
            )
        """))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_rbac_policies_slug ON rbac_policies(slug)"
        ))

    # ═══════════════════════════════════════════════════════════════════
    # 2. RBAC_RULES
    # ═══════════════════════════════════════════════════════════════════
    if not _table_exists('rbac_rules'):
        conn.execute(sa.text("""
            CREATE TABLE rbac_rules (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                rbac_policy_id UUID NOT NULL REFERENCES rbac_policies(id) ON DELETE CASCADE,
                level VARCHAR(20) NOT NULL,
                level_id UUID,
                resource_type VARCHAR(20) NOT NULL,
                resource_id UUID NOT NULL,
                effect VARCHAR(10) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,

                CONSTRAINT uq_rbac_rule_unique
                    UNIQUE (rbac_policy_id, level, level_id, resource_type, resource_id),

                CONSTRAINT ck_rbac_rule_level
                    CHECK (level IN ('platform', 'tenant', 'user')),

                CONSTRAINT ck_rbac_rule_resource_type
                    CHECK (resource_type IN ('agent', 'toolgroup', 'tool', 'instance')),

                CONSTRAINT ck_rbac_rule_effect
                    CHECK (effect IN ('allow', 'deny')),

                CONSTRAINT ck_rbac_rule_level_id
                    CHECK (
                        (level = 'platform' AND level_id IS NULL) OR
                        (level IN ('tenant', 'user') AND level_id IS NOT NULL)
                    )
            )
        """))

        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_rbac_rules_policy "
            "ON rbac_rules(rbac_policy_id)"
        ))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_rbac_rule_resource "
            "ON rbac_rules(resource_type, resource_id, effect)"
        ))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_rbac_rule_level "
            "ON rbac_rules(level, level_id)"
        ))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_rbac_rule_lookup "
            "ON rbac_rules(level, level_id, resource_type, resource_id)"
        ))

    # ═══════════════════════════════════════════════════════════════════
    # 3. PLATFORM_SETTINGS (singleton)
    # ═══════════════════════════════════════════════════════════════════
    if not _table_exists('platform_settings'):
        conn.execute(sa.text("""
            CREATE TABLE platform_settings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                default_policy_id UUID REFERENCES policies(id) ON DELETE SET NULL,
                default_limit_id UUID REFERENCES limits(id) ON DELETE SET NULL,
                default_rbac_policy_id UUID REFERENCES rbac_policies(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """))

        # Seed singleton row
        conn.execute(sa.text("""
            INSERT INTO platform_settings (id)
            VALUES (gen_random_uuid())
        """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS platform_settings CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS rbac_rules CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS rbac_policies CASCADE"))
