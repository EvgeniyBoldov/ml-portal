"""Typed embedding/rerank capabilities; no Qdrant data is changed."""
from alembic import op
import sqlalchemy as sa

revision = "0186"
down_revision = "0185"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("models", sa.Column("embedding_dimensions", sa.Integer(), nullable=True))
    op.add_column("models", sa.Column("max_input_tokens", sa.Integer(), nullable=True))
    op.add_column("models", sa.Column("vector_normalized", sa.Boolean(), nullable=True))
    op.add_column("models", sa.Column("capabilities_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("""UPDATE models SET embedding_dimensions = CASE
        WHEN COALESCE(extra_config->>'vector_dim', extra_config->>'dimensions',
                      extra_config->'manifest'->>'dimensions') ~ '^[0-9]{1,8}$'
        THEN NULLIF(COALESCE(extra_config->>'vector_dim', extra_config->>'dimensions',
                            extra_config->'manifest'->>'dimensions')::int, 0) END
        WHERE type = 'EMBEDDING'""")
    op.execute("""UPDATE models SET max_input_tokens = CASE
        WHEN COALESCE(extra_config->>'max_tokens', extra_config->'manifest'->>'max_tokens') ~ '^[0-9]{1,8}$'
        THEN NULLIF(COALESCE(extra_config->>'max_tokens', extra_config->'manifest'->>'max_tokens')::int, 0) END
        WHERE type IN ('EMBEDDING', 'RERANKER')""")
    op.create_check_constraint("ck_models_embedding_dimensions_positive", "models", "embedding_dimensions IS NULL OR embedding_dimensions > 0")
    op.create_check_constraint("ck_models_max_input_tokens_positive", "models", "max_input_tokens IS NULL OR max_input_tokens > 0")


def downgrade() -> None:
    op.drop_constraint("ck_models_max_input_tokens_positive", "models", type_="check")
    op.drop_constraint("ck_models_embedding_dimensions_positive", "models", type_="check")
    for name in ["capabilities_checked_at", "vector_normalized", "max_input_tokens", "embedding_dimensions"]:
        op.drop_column("models", name)
