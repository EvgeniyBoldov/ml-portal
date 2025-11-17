"""Alter model_registry (global flag) and tenants (extra_embed_model)

Revision ID: 0013_alter_models_and_tenants
Revises: 0012_create_model_registry_table
Create Date: 2025-11-15
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0013_alter_models_and_tenants"
down_revision = "0012_create_model_registry_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # model_registry: rename default_for_new -> global (as a new column mapped as "global")
    with op.batch_alter_table("model_registry") as batch_op:
        batch_op.add_column(sa.Column("global", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        # Drop old column if existed
        try:
            batch_op.drop_column("default_for_new")
        except Exception:
            pass

    # Ensure partial unique indexes for global per modality (text, rerank)
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_model_registry_global_text
        ON model_registry (modality)
        WHERE "global" = true AND modality = 'text';
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_model_registry_global_rerank
        ON model_registry (modality)
        WHERE "global" = true AND modality = 'rerank';
        """
    )

    # tenants: drop rerank_model, embed_models; add extra_embed_model with FK to model_registry.model
    with op.batch_alter_table("tenants") as batch_op:
        # Drop legacy columns if they exist
        try:
            batch_op.drop_column("rerank_model")
        except Exception:
            pass
        try:
            batch_op.drop_column("embed_models")
        except Exception:
            pass
        batch_op.add_column(sa.Column("extra_embed_model", sa.String(length=255), nullable=True))
        batch_op.create_foreign_key(
            "fk_tenants_extra_embed_model",
            "model_registry",
            ["extra_embed_model"],
            ["model"],
            ondelete=None,
        )


def downgrade() -> None:
    # tenants: revert extra_embed_model and restore old columns (best-effort)
    with op.batch_alter_table("tenants") as batch_op:
        try:
            batch_op.drop_constraint("fk_tenants_extra_embed_model", type_="foreignkey")
        except Exception:
            pass
        try:
            batch_op.drop_column("extra_embed_model")
        except Exception:
            pass
        batch_op.add_column(sa.Column("embed_models", postgresql.ARRAY(sa.String()), nullable=True))
        batch_op.add_column(sa.Column("rerank_model", sa.String(length=255), nullable=True))

    # model_registry: drop global, restore default_for_new
    with op.batch_alter_table("model_registry") as batch_op:
        try:
            batch_op.drop_column("global")
        except Exception:
            pass
        batch_op.add_column(sa.Column("default_for_new", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    # Drop partial unique indexes
    op.execute("DROP INDEX IF EXISTS uq_model_registry_global_text;")
    op.execute("DROP INDEX IF EXISTS uq_model_registry_global_rerank;")
