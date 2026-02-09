"""Tool system v2: refactor tools, tool_groups, tool_instances, credentials.

- tool_groups: add type, description_for_router; drop is_active, updated_at
- tools: add current_version_id, kind, tags; drop legacy fields
- tool_instances: add url, config; drop legacy fields; rename connection_config
- credential_sets -> credentials: owner-based model

Revision ID: 0065
Revises: 0064
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0065'
down_revision = '0064'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── helpers ──────────────────────────────────────────────────────────
    def _col_exists(table: str, column: str) -> bool:
        return conn.execute(sa.text(
            "SELECT 1 FROM information_schema.columns "
            f"WHERE table_name = '{table}' AND column_name = '{column}'"
        )).fetchone() is not None

    def _table_exists(table: str) -> bool:
        return conn.execute(sa.text(
            "SELECT 1 FROM information_schema.tables "
            f"WHERE table_name = '{table}'"
        )).fetchone() is not None

    def _constraint_exists(constraint: str) -> bool:
        return conn.execute(sa.text(
            "SELECT 1 FROM information_schema.table_constraints "
            f"WHERE constraint_name = '{constraint}'"
        )).fetchone() is not None

    # ═══════════════════════════════════════════════════════════════════
    # 1. TOOL_GROUPS: add type, description_for_router; drop is_active, updated_at
    # ═══════════════════════════════════════════════════════════════════
    if not _col_exists('tool_groups', 'type'):
        conn.execute(sa.text(
            "ALTER TABLE tool_groups ADD COLUMN type varchar(50)"
        ))
    if not _col_exists('tool_groups', 'description_for_router'):
        conn.execute(sa.text(
            "ALTER TABLE tool_groups ADD COLUMN description_for_router text"
        ))
    conn.execute(sa.text("ALTER TABLE tool_groups DROP COLUMN IF EXISTS is_active"))
    conn.execute(sa.text("ALTER TABLE tool_groups DROP COLUMN IF EXISTS updated_at"))

    # ═══════════════════════════════════════════════════════════════════
    # 2. TOOLS: add current_version_id, kind, tags; drop legacy fields
    # ═══════════════════════════════════════════════════════════════════

    # Rename recommended_release_id -> current_version_id
    if _col_exists('tools', 'recommended_release_id') and not _col_exists('tools', 'current_version_id'):
        conn.execute(sa.text(
            "ALTER TABLE tools RENAME COLUMN recommended_release_id TO current_version_id"
        ))

    # Add kind column
    if not _col_exists('tools', 'kind'):
        conn.execute(sa.text(
            "ALTER TABLE tools ADD COLUMN kind varchar(10) NOT NULL DEFAULT 'read'"
        ))

    # Add tags column
    if not _col_exists('tools', 'tags'):
        conn.execute(sa.text(
            "ALTER TABLE tools ADD COLUMN tags text[]"
        ))

    # Drop legacy columns
    for col in ['input_schema', 'output_schema', 'config', 'type',
                'is_active', 'name_for_llm', 'description', 'updated_at']:
        conn.execute(sa.text(f"ALTER TABLE tools DROP COLUMN IF EXISTS {col}"))

    # Add unique constraint (group_id, slug) if not exists
    if not _constraint_exists('uq_tool_group_slug'):
        conn.execute(sa.text(
            "ALTER TABLE tools ADD CONSTRAINT uq_tool_group_slug "
            "UNIQUE (tool_group_id, slug)"
        ))

    # ═══════════════════════════════════════════════════════════════════
    # 3. TOOL_INSTANCES: add url, rename connection_config->config, drop legacy
    # ═══════════════════════════════════════════════════════════════════

    # Add url column
    if not _col_exists('tool_instances', 'url'):
        conn.execute(sa.text(
            "ALTER TABLE tool_instances ADD COLUMN url text NOT NULL DEFAULT ''"
        ))
        # Migrate: extract url from connection_config if exists
        if _col_exists('tool_instances', 'connection_config'):
            conn.execute(sa.text("""
                UPDATE tool_instances
                SET url = COALESCE(connection_config->>'url', connection_config->>'base_url', '')
                WHERE connection_config IS NOT NULL
            """))

    # Rename connection_config -> config (if not already done)
    if _col_exists('tool_instances', 'connection_config') and not _col_exists('tool_instances', 'config'):
        conn.execute(sa.text(
            "ALTER TABLE tool_instances RENAME COLUMN connection_config TO config"
        ))
    elif _col_exists('tool_instances', 'connection_config') and _col_exists('tool_instances', 'config'):
        conn.execute(sa.text(
            "ALTER TABLE tool_instances DROP COLUMN IF EXISTS connection_config"
        ))

    # Drop legacy columns
    for col in ['slug', 'instance_metadata', 'instance_type',
                'last_health_check_at', 'health_check_error', 'updated_at']:
        conn.execute(sa.text(f"ALTER TABLE tool_instances DROP COLUMN IF EXISTS {col}"))

    # Add unique constraint (group_id, url) if not exists
    if not _constraint_exists('uq_tool_instance_group_url'):
        # First handle potential duplicates
        conn.execute(sa.text("""
            DELETE FROM tool_instances a USING tool_instances b
            WHERE a.id > b.id
              AND a.tool_group_id = b.tool_group_id
              AND a.url = b.url
        """))
        conn.execute(sa.text(
            "ALTER TABLE tool_instances ADD CONSTRAINT uq_tool_instance_group_url "
            "UNIQUE (tool_group_id, url)"
        ))

    # ═══════════════════════════════════════════════════════════════════
    # 4. CREDENTIALS: create new table, migrate from credential_sets
    # ═══════════════════════════════════════════════════════════════════
    if not _table_exists('credentials'):
        conn.execute(sa.text("""
            CREATE TABLE credentials (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                instance_id UUID NOT NULL REFERENCES tool_instances(id) ON DELETE CASCADE,
                owner_user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                owner_tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
                owner_platform boolean NOT NULL DEFAULT false,
                auth_type varchar(50) NOT NULL,
                encrypted_payload text NOT NULL,
                is_active boolean NOT NULL DEFAULT true,
                created_at timestamptz NOT NULL DEFAULT now(),
                CONSTRAINT ck_credential_single_owner CHECK (
                    (owner_platform::int +
                     (owner_user_id IS NOT NULL)::int +
                     (owner_tenant_id IS NOT NULL)::int) = 1
                ),
                CONSTRAINT ck_credential_auth_type CHECK (
                    auth_type IN ('token', 'basic', 'oauth', 'api_key')
                )
            )
        """))

        # Create partial indexes for fast lookup
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_credential_instance "
            "ON credentials(instance_id)"
        ))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_credential_user_lookup "
            "ON credentials(owner_user_id, instance_id) WHERE is_active = true"
        ))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_credential_tenant_lookup "
            "ON credentials(owner_tenant_id, instance_id) WHERE is_active = true"
        ))
        conn.execute(sa.text(
            "CREATE INDEX IF NOT EXISTS ix_credential_platform_lookup "
            "ON credentials(owner_platform, instance_id) WHERE is_active = true"
        ))

        # Migrate data from credential_sets if exists
        if _table_exists('credential_sets'):
            conn.execute(sa.text("""
                INSERT INTO credentials (id, instance_id, owner_user_id, owner_tenant_id,
                    owner_platform, auth_type, encrypted_payload, is_active, created_at)
                SELECT
                    id,
                    tool_instance_id,
                    CASE WHEN scope = 'user' THEN user_id ELSE NULL END,
                    CASE WHEN scope = 'tenant' THEN tenant_id ELSE NULL END,
                    CASE WHEN scope = 'default' THEN true ELSE false END,
                    auth_type,
                    encrypted_payload,
                    is_active,
                    created_at
                FROM credential_sets
                WHERE tool_instance_id IS NOT NULL
            """))

    # Drop old credential_sets table
    conn.execute(sa.text("DROP TABLE IF EXISTS credential_sets CASCADE"))


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Recreate credential_sets from credentials
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS credential_sets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tool_instance_id UUID NOT NULL REFERENCES tool_instances(id) ON DELETE CASCADE,
            scope varchar(20) NOT NULL,
            tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            auth_type varchar(50) NOT NULL,
            encrypted_payload text NOT NULL,
            is_active boolean NOT NULL DEFAULT true,
            is_default boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """))

    # Migrate back
    conn.execute(sa.text("""
        INSERT INTO credential_sets (id, tool_instance_id, scope, tenant_id, user_id,
            auth_type, encrypted_payload, is_active, created_at)
        SELECT
            id,
            instance_id,
            CASE
                WHEN owner_platform THEN 'default'
                WHEN owner_tenant_id IS NOT NULL THEN 'tenant'
                WHEN owner_user_id IS NOT NULL THEN 'user'
            END,
            owner_tenant_id,
            owner_user_id,
            auth_type,
            encrypted_payload,
            is_active,
            created_at
        FROM credentials
    """))

    conn.execute(sa.text("DROP TABLE IF EXISTS credentials CASCADE"))

    # 2. Restore tool_instances columns
    conn.execute(sa.text(
        "ALTER TABLE tool_instances ADD COLUMN IF NOT EXISTS slug varchar(255)"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tool_instances ADD COLUMN IF NOT EXISTS instance_metadata jsonb DEFAULT '{}'"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tool_instances ADD COLUMN IF NOT EXISTS instance_type varchar(20) DEFAULT 'http'"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tool_instances ADD COLUMN IF NOT EXISTS last_health_check_at timestamptz"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tool_instances ADD COLUMN IF NOT EXISTS health_check_error text"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tool_instances ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now()"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tool_instances DROP CONSTRAINT IF EXISTS uq_tool_instance_group_url"
    ))

    # Rename config back to connection_config
    conn.execute(sa.text(
        "ALTER TABLE tool_instances RENAME COLUMN config TO connection_config"
    ))
    conn.execute(sa.text("ALTER TABLE tool_instances DROP COLUMN IF EXISTS url"))

    # 3. Restore tools columns
    conn.execute(sa.text(
        "ALTER TABLE tools ADD COLUMN IF NOT EXISTS input_schema jsonb DEFAULT '{}'"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tools ADD COLUMN IF NOT EXISTS output_schema jsonb"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tools ADD COLUMN IF NOT EXISTS config jsonb DEFAULT '{}'"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tools ADD COLUMN IF NOT EXISTS type varchar(50) DEFAULT 'builtin'"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tools ADD COLUMN IF NOT EXISTS is_active boolean DEFAULT true"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tools ADD COLUMN IF NOT EXISTS name_for_llm varchar(255)"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tools ADD COLUMN IF NOT EXISTS description text"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tools ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now()"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tools DROP CONSTRAINT IF EXISTS uq_tool_group_slug"
    ))

    # Rename current_version_id back
    conn.execute(sa.text(
        "ALTER TABLE tools RENAME COLUMN current_version_id TO recommended_release_id"
    ))
    conn.execute(sa.text("ALTER TABLE tools DROP COLUMN IF EXISTS kind"))
    conn.execute(sa.text("ALTER TABLE tools DROP COLUMN IF EXISTS tags"))

    # 4. Restore tool_groups columns
    conn.execute(sa.text(
        "ALTER TABLE tool_groups ADD COLUMN IF NOT EXISTS is_active boolean DEFAULT true"
    ))
    conn.execute(sa.text(
        "ALTER TABLE tool_groups ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT now()"
    ))
    conn.execute(sa.text("ALTER TABLE tool_groups DROP COLUMN IF EXISTS type"))
    conn.execute(sa.text("ALTER TABLE tool_groups DROP COLUMN IF EXISTS description_for_router"))
