"""Pin legacy-vector compatibility before any encoder configuration changes."""
from types import SimpleNamespace

from alembic import op
import sqlalchemy as sa

revision = "0187"
down_revision = "0186"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.services.model_capabilities import ModelCapabilities, embedding_fingerprint
    connection = op.get_bind()
    rows = connection.execute(sa.text("""SELECT id, alias, provider_model_name,
        model_version, embedding_dimensions, max_input_tokens, vector_normalized, extra_config
        FROM models WHERE type = 'EMBEDDING' AND deleted_at IS NULL""")).mappings().all()
    for row in rows:
        model = SimpleNamespace(**row)
        try:
            caps = ModelCapabilities.from_model(model)
        except (ValueError, TypeError):
            # Invalid historical metadata must not prevent upgrading the DB.
            continue
        # Unknown legacy characteristics are not guessed from vector length.
        if not (caps.embedding_dimensions and caps.max_input_tokens and caps.model_version):
            continue
        extra = dict(row["extra_config"] or {})
        extra["legacy_embedding_fingerprint"] = embedding_fingerprint(model, caps, include_input_policy=False)
        connection.execute(sa.text("UPDATE models SET extra_config=:extra WHERE id=:id").bindparams(
            sa.bindparam("extra", type_=sa.JSON())), {"id":row["id"], "extra":extra})


def downgrade() -> None:
    op.execute("""UPDATE models SET extra_config = (extra_config::jsonb - 'legacy_embedding_fingerprint')::json
                  WHERE extra_config::jsonb ? 'legacy_embedding_fingerprint'""")
