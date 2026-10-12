"""Dedicated LongMemory encoder and transactional reindex requests."""
from alembic import op
import sqlalchemy as sa
from uuid import uuid4

revision = "0184"
down_revision = "0183"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("models", sa.Column("use_for_long_memory", sa.Boolean(), nullable=False, server_default="false"))
    op.execute("""UPDATE models SET use_for_long_memory = true WHERE id = (
        SELECT id FROM models WHERE type = 'EMBEDDING' AND default_for_type IS TRUE
        AND enabled IS TRUE AND deleted_at IS NULL ORDER BY created_at LIMIT 1)""")
    op.create_check_constraint("ck_models_long_memory_embedding", "models",
                               "NOT use_for_long_memory OR (type = 'EMBEDDING' AND deleted_at IS NULL)")
    op.create_index("uq_models_long_memory_embedding", "models", ["use_for_long_memory"],
                    unique=True, postgresql_where=sa.text("use_for_long_memory"))
    op.create_table("long_memory_reindex_requests",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("model_id", sa.UUID(), sa.ForeignKey("models.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.get_bind().execute(sa.text("""INSERT INTO long_memory_reindex_requests (id, model_id)
        SELECT :id, id FROM models WHERE use_for_long_memory IS TRUE"""), {"id": uuid4()})


def downgrade() -> None:
    op.drop_table("long_memory_reindex_requests")
    op.drop_index("uq_models_long_memory_embedding", table_name="models")
    op.drop_constraint("ck_models_long_memory_embedding", "models", type_="check")
    op.drop_column("models", "use_for_long_memory")
