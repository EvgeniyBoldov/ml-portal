"""Cleanup unused models and setup reranker

Revision ID: 0019_cleanup_and_rerank
Revises: 0018_add_system_models
Create Date: 2025-11-29

1. Delete unimplemented models (OCR, ASR)
2. Delete unimplemented local embeddings (multilingual, bge)
3. Update reranker base_url to new service
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0019_cleanup_and_rerank"
down_revision = "0018_add_system_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Delete unimplemented models
    # Deleting system models requires ignoring the protection? 
    # No, database constraint doesn't exist, it's app logic. SQL DELETE works.
    op.execute("DELETE FROM models WHERE type IN ('OCR', 'ASR')")
    
    # 2. Delete unimplemented local embeddings (files not present in dev env)
    op.execute("DELETE FROM models WHERE alias IN ('embed.local.multilingual', 'embed.local.bge')")
    
    # 3. Update reranker to point to new service
    op.execute("""
        UPDATE models 
        SET base_url = 'http://rerank:8002',
            provider_model_name = 'cross-encoder/ms-marco-MiniLM-L-6-v2',
            extra_config = CAST('{"top_k": 5}' AS JSONB)
        WHERE alias = 'reranker.local.default'
    """)


def downgrade() -> None:
    # Reverting deletes is hard without data.
    # Reverting update
    op.execute("""
        UPDATE models 
        SET base_url = 'http://emb:8001'
        WHERE alias = 'reranker.local.default'
    """)
    # We don't restore deleted rows as they were placeholders.
