"""Refactor model registry to new provider architecture

Revision ID: 0017_model_registry_refactor
Revises: 0016_cleanup_status
Create Date: 2025-11-29

1. Drop model_registry table (and remove extra_embed_model from tenants)
2. Create models table
3. Add embedding_model_alias to tenants
4. Seed default models
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision = "0017_model_registry_refactor"
down_revision = "0016_cleanup_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Remove FK from tenants to model_registry
    # We first drop the constraint, then drop the column
    with op.batch_alter_table("tenants") as batch_op:
        # Try to drop constraint if it exists (name might vary)
        try:
            batch_op.drop_constraint("fk_tenants_extra_embed_model", type_="foreignkey")
        except Exception:
            # Fallback: try to find and drop by inspecting (not possible in batch mode directly easily)
            # Assuming the name from 0013 migration
            pass
        batch_op.drop_column("extra_embed_model")

    # 2. Drop model_registry table
    op.drop_table("model_registry")
    # Also drop related types if any created
    op.execute("DROP TYPE IF EXISTS model_type")
    op.execute("DROP TYPE IF EXISTS model_status")
    op.execute("DROP TYPE IF EXISTS health_status")

    # 3. Create new models table
    # Create Enums first
    model_type = sa.Enum("llm_chat", "embedding", name="model_type")
    model_status = sa.Enum("available", "unavailable", "deprecated", "maintenance", name="model_status")
    health_status = sa.Enum("healthy", "degraded", "unavailable", name="health_status")
    
    # Note: in Postgres, Enums are created automatically by SQLAlchemy if using create_type=True
    # but here we use them in Column definition
    
    op.create_table(
        "models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("alias", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", model_type, nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_model_name", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("api_key_ref", sa.String(length=255), nullable=True),
        sa.Column("extra_config", postgresql.JSONB, nullable=True),
        sa.Column("status", model_status, nullable=False, server_default="available"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("default_for_type", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("model_version", sa.String(length=50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_status", health_status, nullable=True),
        sa.Column("health_error", sa.Text(), nullable=True),
        sa.Column("health_latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    
    # Indexes
    op.create_index("ix_models_alias", "models", ["alias"], unique=True)
    op.create_index("ix_models_type", "models", ["type"])
    
    # 4. Update tenants table
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(sa.Column("embedding_model_alias", sa.String(length=100), nullable=True))
        batch_op.create_foreign_key(
            "fk_tenants_embedding_model_alias",
            "models",
            ["embedding_model_alias"],
            ["alias"],
        )

    # 5. Seed default models
    # Use raw SQL to avoid importing app code
    op.execute(
        """
        INSERT INTO models (
            id, alias, name, type, provider, provider_model_name, base_url, 
            status, enabled, default_for_type, created_at, updated_at
        ) VALUES 
        (
            gen_random_uuid(), 
            'llm.chat.default', 
            'Groq Llama 3.1 70B', 
            'llm_chat', 
            'groq', 
            'llama-3.1-70b-versatile', 
            'https://api.groq.com/openai/v1', 
            'available', 
            true, 
            true, 
            NOW(), 
            NOW()
        ),
        (
            gen_random_uuid(), 
            'embed.default', 
            'OpenAI text-embedding-3-large', 
            'embedding', 
            'openai', 
            'text-embedding-3-large', 
            'https://api.openai.com/v1', 
            'available', 
            true, 
            true, 
            NOW(), 
            NOW()
        )
        """
    )


def downgrade() -> None:
    # 1. Remove column from tenants
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.drop_constraint("fk_tenants_embedding_model_alias", type_="foreignkey")
        batch_op.drop_column("embedding_model_alias")

    # 2. Drop models table
    op.drop_index("ix_models_type", table_name="models")
    op.drop_index("ix_models_alias", table_name="models")
    op.drop_table("models")
    
    op.execute("DROP TYPE IF EXISTS model_type")
    op.execute("DROP TYPE IF EXISTS model_status")
    op.execute("DROP TYPE IF EXISTS health_status")

    # 3. Recreate model_registry table (simplified restoration)
    op.create_table(
        "model_registry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("modality", sa.String(length=20), nullable=False),
        sa.Column("state", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("vector_dim", sa.Integer(), nullable=True),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("global", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_model_registry_model", "model_registry", ["model"], unique=True)
    
    # 4. Restore tenants column
    with op.batch_alter_table("tenants") as batch_op:
        batch_op.add_column(sa.Column("extra_embed_model", sa.String(length=255), nullable=True))
        batch_op.create_foreign_key(
            "fk_tenants_extra_embed_model",
            "model_registry",
            ["extra_embed_model"],
            ["model"],
        )
