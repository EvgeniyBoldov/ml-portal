"""Agent v2: create agent_versions table, refactor agents and agent_bindings.

- Create agent_versions table (prompt, policy_id, limit_id, version, status)
- Remove old columns from agents (system_prompt_slug, policy_id, limit_id,
  capabilities, supports_partial_mode, generation_config, is_active, enable_logging)
- Add current_version_id to agents
- Refactor agent_bindings: agent_id -> agent_version_id, update credential_strategy,
  remove required/updated_at columns
- Migrate existing agent data into agent_versions

Revision ID: 0064
Revises: 0063
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0064'
down_revision = '0063'
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

    # ── 1. Create agent_versions table (idempotent) ─────────────────────
    if not _table_exists('agent_versions'):
        op.create_table(
            'agent_versions',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                      server_default=sa.text('gen_random_uuid()')),
            sa.Column('agent_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('agents.id', ondelete='CASCADE'), nullable=False, index=True),
            sa.Column('version', sa.Integer, nullable=False),
            sa.Column('status', sa.String(20), nullable=False, server_default='draft', index=True),
            sa.Column('prompt', sa.Text, nullable=False, server_default=''),
            sa.Column('policy_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('policies.id', ondelete='SET NULL'), nullable=True, index=True),
            sa.Column('limit_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('limits.id', ondelete='SET NULL'), nullable=True, index=True),
            sa.Column('parent_version_id', postgresql.UUID(as_uuid=True),
                      sa.ForeignKey('agent_versions.id', ondelete='SET NULL'), nullable=True),
            sa.Column('notes', sa.Text, nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.UniqueConstraint('agent_id', 'version', name='uix_agent_version'),
        )

    # ── 2. Migrate data into agent_versions (only if empty) ─────────────
    has_rows = conn.execute(sa.text(
        "SELECT 1 FROM agent_versions LIMIT 1"
    )).fetchone() is not None

    if not has_rows:
        # Check which old columns still exist for data migration
        policy_expr = "a.policy_id" if _col_exists('agents', 'policy_id') else "NULL::uuid"
        limit_expr = "a.limit_id" if _col_exists('agents', 'limit_id') else "NULL::uuid"

        if _col_exists('agents', 'system_prompt_slug'):
            join_clause = (
                "LEFT JOIN prompts p ON p.slug = a.system_prompt_slug "
                "LEFT JOIN prompt_versions pv ON pv.id = p.recommended_version_id"
            )
            prompt_expr = "COALESCE(pv.template, '')"
        else:
            join_clause = ""
            prompt_expr = "''"

        conn.execute(sa.text(f"""
            INSERT INTO agent_versions (id, agent_id, version, status, prompt, policy_id, limit_id, notes)
            SELECT
                gen_random_uuid(),
                a.id,
                1,
                'active',
                {prompt_expr},
                {policy_expr},
                {limit_expr},
                'Migrated from v1 agent'
            FROM agents a
            {join_clause}
        """))

    # ── 3. Add current_version_id to agents ─────────────────────────────
    conn.execute(sa.text(
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS current_version_id UUID"
    ))

    # Clear stale current_version_id values (from previous partial migration)
    conn.execute(sa.text("""
        UPDATE agents SET current_version_id = NULL
        WHERE current_version_id IS NOT NULL
          AND current_version_id NOT IN (SELECT id FROM agent_versions)
    """))

    # Update current_version_id (only where NULL)
    conn.execute(sa.text("""
        UPDATE agents SET current_version_id = av.id
        FROM agent_versions av
        WHERE av.agent_id = agents.id AND av.version = 1
          AND agents.current_version_id IS NULL
    """))

    # Add FK constraint (idempotent)
    if not _constraint_exists('fk_agents_current_version_id'):
        conn.execute(sa.text(
            "ALTER TABLE agents ADD CONSTRAINT fk_agents_current_version_id "
            "FOREIGN KEY (current_version_id) REFERENCES agent_versions(id) ON DELETE SET NULL"
        ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_agents_current_version_id ON agents(current_version_id)"
    ))

    # ── 4. Refactor agent_bindings: agent_id -> agent_version_id ────────
    conn.execute(sa.text(
        "ALTER TABLE agent_bindings ADD COLUMN IF NOT EXISTS agent_version_id UUID"
    ))

    # Migrate agent_id -> agent_version_id (only if agent_id column still exists)
    if _col_exists('agent_bindings', 'agent_id'):
        conn.execute(sa.text("""
            UPDATE agent_bindings ab
            SET agent_version_id = av.id
            FROM agent_versions av
            WHERE av.agent_id = ab.agent_id AND av.version = 1
              AND ab.agent_version_id IS NULL
        """))

        # Drop old constraints
        conn.execute(sa.text(
            "ALTER TABLE agent_bindings DROP CONSTRAINT IF EXISTS uq_agent_tool"
        ))
        conn.execute(sa.text(
            "ALTER TABLE agent_bindings DROP CONSTRAINT IF EXISTS agent_bindings_agent_id_fkey"
        ))
        conn.execute(sa.text("DROP INDEX IF EXISTS ix_agent_bindings_agent_id"))

        # Drop agent_id column
        conn.execute(sa.text(
            "ALTER TABLE agent_bindings DROP COLUMN IF EXISTS agent_id"
        ))

    # Delete orphan bindings
    conn.execute(sa.text(
        "DELETE FROM agent_bindings WHERE agent_version_id IS NULL"
    ))

    # Make NOT NULL (idempotent — ALTER COLUMN SET NOT NULL is safe to repeat)
    conn.execute(sa.text(
        "ALTER TABLE agent_bindings ALTER COLUMN agent_version_id SET NOT NULL"
    ))

    # Add FK + index (idempotent)
    if not _constraint_exists('agent_bindings_agent_version_id_fkey'):
        conn.execute(sa.text(
            "ALTER TABLE agent_bindings ADD CONSTRAINT agent_bindings_agent_version_id_fkey "
            "FOREIGN KEY (agent_version_id) REFERENCES agent_versions(id) ON DELETE CASCADE"
        ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_agent_bindings_agent_version_id "
        "ON agent_bindings(agent_version_id)"
    ))

    # Add unique constraint (idempotent)
    if not _constraint_exists('uq_agent_version_tool'):
        conn.execute(sa.text(
            "ALTER TABLE agent_bindings ADD CONSTRAINT uq_agent_version_tool "
            "UNIQUE (agent_version_id, tool_id)"
        ))

    # Update credential_strategy values to v2 format (safe to repeat)
    conn.execute(sa.text("""
        UPDATE agent_bindings SET credential_strategy = CASE credential_strategy
            WHEN 'user_only' THEN 'USER_ONLY'
            WHEN 'tenant_only' THEN 'TENANT_ONLY'
            WHEN 'default_only' THEN 'PLATFORM_ONLY'
            WHEN 'prefer_user' THEN 'USER_THEN_TENANT'
            WHEN 'prefer_tenant' THEN 'TENANT_THEN_PLATFORM'
            WHEN 'any' THEN 'ANY'
            ELSE credential_strategy
        END
    """))

    # Widen credential_strategy column
    conn.execute(sa.text(
        "ALTER TABLE agent_bindings ALTER COLUMN credential_strategy TYPE varchar(30)"
    ))

    # Make tool_instance_id nullable
    conn.execute(sa.text(
        "ALTER TABLE agent_bindings ALTER COLUMN tool_instance_id DROP NOT NULL"
    ))

    # Drop old columns from agent_bindings
    conn.execute(sa.text("ALTER TABLE agent_bindings DROP COLUMN IF EXISTS required"))
    conn.execute(sa.text("ALTER TABLE agent_bindings DROP COLUMN IF EXISTS updated_at"))

    # ── 5. Drop old columns from agents ─────────────────────────────────
    conn.execute(sa.text(
        "ALTER TABLE agents DROP CONSTRAINT IF EXISTS agents_policy_id_fkey"
    ))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_agents_policy_id"))
    conn.execute(sa.text(
        "ALTER TABLE agents DROP CONSTRAINT IF EXISTS agents_limit_id_fkey"
    ))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_agents_limit_id"))

    for col in [
        'system_prompt_slug', 'policy_id', 'limit_id',
        'capabilities', 'supports_partial_mode', 'generation_config',
        'is_active', 'enable_logging',
    ]:
        conn.execute(sa.text(f"ALTER TABLE agents DROP COLUMN IF EXISTS {col}"))


def downgrade() -> None:
    conn = op.get_bind()

    # 1. Re-add old columns to agents
    conn.execute(sa.text(
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS system_prompt_slug varchar(255)"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS policy_id UUID "
        "REFERENCES policies(id) ON DELETE SET NULL"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS limit_id UUID "
        "REFERENCES limits(id) ON DELETE SET NULL"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS capabilities jsonb DEFAULT '[]'"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS supports_partial_mode boolean DEFAULT false"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS generation_config jsonb DEFAULT '{}'"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_active boolean DEFAULT true"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agents ADD COLUMN IF NOT EXISTS enable_logging boolean DEFAULT true"
    ))

    # 2. Restore data from agent_versions
    conn.execute(sa.text("""
        UPDATE agents SET
            policy_id = av.policy_id,
            limit_id = av.limit_id,
            system_prompt_slug = 'migrated'
        FROM agent_versions av
        WHERE av.id = agents.current_version_id
    """))

    # 3. Restore agent_bindings: agent_version_id -> agent_id
    conn.execute(sa.text(
        "ALTER TABLE agent_bindings ADD COLUMN IF NOT EXISTS agent_id UUID"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agent_bindings ADD COLUMN IF NOT EXISTS required boolean DEFAULT false"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agent_bindings ADD COLUMN IF NOT EXISTS updated_at "
        "timestamptz DEFAULT now()"
    ))

    conn.execute(sa.text("""
        UPDATE agent_bindings ab SET agent_id = av.agent_id
        FROM agent_versions av WHERE av.id = ab.agent_version_id
    """))

    conn.execute(sa.text(
        "ALTER TABLE agent_bindings DROP CONSTRAINT IF EXISTS uq_agent_version_tool"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agent_bindings DROP CONSTRAINT IF EXISTS agent_bindings_agent_version_id_fkey"
    ))
    conn.execute(sa.text(
        "DROP INDEX IF EXISTS ix_agent_bindings_agent_version_id"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agent_bindings DROP COLUMN IF EXISTS agent_version_id"
    ))

    conn.execute(sa.text(
        "ALTER TABLE agent_bindings ALTER COLUMN agent_id SET NOT NULL"
    ))
    conn.execute(sa.text(
        "ALTER TABLE agent_bindings ADD CONSTRAINT agent_bindings_agent_id_fkey "
        "FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_agent_bindings_agent_id ON agent_bindings(agent_id)"
    ))

    # 4. Drop current_version_id from agents
    conn.execute(sa.text(
        "ALTER TABLE agents DROP CONSTRAINT IF EXISTS fk_agents_current_version_id"
    ))
    conn.execute(sa.text("DROP INDEX IF EXISTS ix_agents_current_version_id"))
    conn.execute(sa.text("ALTER TABLE agents DROP COLUMN IF EXISTS current_version_id"))

    # 5. Drop agent_versions table
    op.drop_table('agent_versions')
