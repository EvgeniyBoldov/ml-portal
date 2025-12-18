"""Remove OpenAI embedding model, keep only local embedding as default

Revision ID: 0031
Revises: 0030
Create Date: 2025-12-13
"""
from alembic import op
import sqlalchemy as sa

revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove OpenAI embedding model
    op.execute("DELETE FROM models WHERE alias = 'embed.default'")
    
    # Ensure local embedding is default
    op.execute("""
        UPDATE models 
        SET default_for_type = true 
        WHERE alias = 'embed.local.minilm'
    """)


def downgrade() -> None:
    # Restore OpenAI embedding model
    op.execute("""
        INSERT INTO models (
            id, alias, name, type, provider, provider_model_name, base_url, 
            status, enabled, default_for_type, is_system, created_at, updated_at
        ) VALUES (
            gen_random_uuid(), 
            'embed.default', 
            'OpenAI text-embedding-3-large', 
            'EMBEDDING', 
            'openai', 
            'text-embedding-3-large', 
            'https://api.openai.com/v1', 
            'AVAILABLE', 
            true, 
            true, 
            true,
            NOW(), 
            NOW()
        )
    """)
    
    # Remove default from local
    op.execute("""
        UPDATE models 
        SET default_for_type = false 
        WHERE alias = 'embed.local.minilm'
    """)
