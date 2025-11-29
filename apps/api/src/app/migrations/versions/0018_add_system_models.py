"""Add system models and update model types

Revision ID: 0018_add_system_models
Revises: 0017_model_registry_refactor
Create Date: 2025-11-29

1. Add new values to model_type enum (RERANKER, OCR, ASR, TTS)
2. Add is_system column to models
3. Seed local system models
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0018_add_system_models"
down_revision = "0017_model_registry_refactor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Update model_type enum
    # Postgres requires separate transactions for ADD VALUE inside a transaction block if not autocommit
    # But Alembic runs in a transaction.
    # We use execution_options to commit before altering type if needed, 
    # or just run raw SQL. Postgres allows ADD VALUE inside transaction since v12.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE model_type ADD VALUE IF NOT EXISTS 'RERANKER'")
        op.execute("ALTER TYPE model_type ADD VALUE IF NOT EXISTS 'OCR'")
        op.execute("ALTER TYPE model_type ADD VALUE IF NOT EXISTS 'ASR'")
        op.execute("ALTER TYPE model_type ADD VALUE IF NOT EXISTS 'TTS'")

    # 2. Add is_system column
    op.add_column('models', sa.Column('is_system', sa.Boolean(), server_default='false', nullable=False))
    
    # 3. Mark existing default models as system
    op.execute("UPDATE models SET is_system = true WHERE alias IN ('llm.chat.default', 'embed.default')")

    # 4. Seed local models
    # Local embeddings served by 'emb' service
    # Local reranker/ocr/asr (placeholders or connected to local services)
    
    models_to_seed = [
        # Local Embeddings
        {
            "alias": "embed.local.minilm",
            "name": "all-MiniLM-L6-v2 (Local)",
            "type": "EMBEDDING",
            "provider": "local",
            "provider_model_name": "all-MiniLM-L6-v2",
            "base_url": "http://emb:8001",
            "status": "AVAILABLE",
            "enabled": True,
            "is_system": True,
            "default_for_type": False,
            "extra_config": '{"batch_size": 32}'
        },
        {
            "alias": "embed.local.multilingual",
            "name": "multilingual-e5-small (Local)",
            "type": "EMBEDDING",
            "provider": "local",
            "provider_model_name": "multilingual-e5-small",
            "base_url": "http://emb:8001",
            "status": "AVAILABLE",
            "enabled": True,
            "is_system": True,
            "default_for_type": False,
            "extra_config": '{"batch_size": 32}'
        },
        {
            "alias": "embed.local.bge",
            "name": "bge-large-en (Local)",
            "type": "EMBEDDING",
            "provider": "local",
            "provider_model_name": "bge-large-en",
            "base_url": "http://emb:8001",
            "status": "AVAILABLE",
            "enabled": True,
            "is_system": True,
            "default_for_type": False,
            "extra_config": '{"batch_size": 16}'
        },
        # Local Reranker (Placeholder/Future)
        {
            "alias": "reranker.local.default",
            "name": "ms-marco-MiniLM-L-6-v2 (Local)",
            "type": "RERANKER",
            "provider": "local",
            "provider_model_name": "cross-encoder/ms-marco-MiniLM-L-6-v2",
            "base_url": "http://emb:8001", # Assuming it will be added to emb service
            "status": "AVAILABLE",
            "enabled": True,
            "is_system": True,
            "default_for_type": True,
            "extra_config": '{"top_k": 5}'
        },
        # Local OCR
        {
            "alias": "ocr.local.default",
            "name": "Tesseract OCR",
            "type": "OCR",
            "provider": "local",
            "provider_model_name": "tesseract",
            "base_url": "local", 
            "status": "AVAILABLE",
            "enabled": True,
            "is_system": True,
            "default_for_type": True,
            "extra_config": '{}'
        },
        # Local ASR
        {
            "alias": "asr.local.default",
            "name": "Whisper Base",
            "type": "ASR",
            "provider": "local",
            "provider_model_name": "whisper-base",
            "base_url": "local", 
            "status": "AVAILABLE",
            "enabled": True,
            "is_system": True,
            "default_for_type": True,
            "extra_config": '{}'
        }
    ]
    
    for m in models_to_seed:
        # Use ON CONFLICT DO UPDATE to allow re-running or updating
        # Use CAST for JSONB to avoid SQLAlchemy parameter parsing issues with ::
        stmt = sa.text("""
            INSERT INTO models (
                id, alias, name, type, provider, provider_model_name, base_url, 
                status, enabled, is_system, default_for_type, extra_config, created_at, updated_at
            ) VALUES (
                gen_random_uuid(), :alias, :name, CAST(:type AS model_type), :provider, :provider_model_name, :base_url,
                CAST(:status AS model_status), :enabled, :is_system, :default_for_type, CAST(:extra_config AS JSONB), NOW(), NOW()
            ) ON CONFLICT (alias) DO UPDATE SET
                name = EXCLUDED.name,
                type = EXCLUDED.type,
                provider = EXCLUDED.provider,
                provider_model_name = EXCLUDED.provider_model_name,
                base_url = EXCLUDED.base_url,
                is_system = EXCLUDED.is_system,
                extra_config = EXCLUDED.extra_config,
                updated_at = NOW()
        """)
        
        op.execute(stmt.bindparams(
            alias=m["alias"],
            name=m["name"],
            type=m["type"],
            provider=m["provider"],
            provider_model_name=m["provider_model_name"],
            base_url=m["base_url"],
            status=m["status"],
            enabled=m["enabled"],
            is_system=m["is_system"],
            default_for_type=m["default_for_type"],
            extra_config=m["extra_config"]
        ))


def downgrade() -> None:
    # 1. Remove seed models
    op.execute("DELETE FROM models WHERE is_system = true AND provider = 'local'")
    
    # 2. Remove is_system column
    op.drop_column('models', 'is_system')
    
    # 3. Revert model_type enum - Cannot remove values from enum in Postgres easily
    # We leave the values as is, it's generally safe.
    pass
