"""Bind collections to data instances via strict FK.

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-21
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _fk_exists(table_name: str, fk_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return any(fk.get("name") == fk_name for fk in inspector.get_foreign_keys(table_name))


def upgrade() -> None:
    fk_name = "fk_collections_data_instance_id_tool_instances"

    if not _column_exists("collections", "data_instance_id"):
        op.add_column(
            "collections",
            sa.Column("data_instance_id", postgresql.UUID(as_uuid=True), nullable=True),
        )

    if not _fk_exists("collections", fk_name):
        op.create_foreign_key(
            fk_name,
            "collections",
            "tool_instances",
            ["data_instance_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    # Legacy backfill from collections.config.bindings[0].instance_id when config exists.
    if _column_exists("collections", "config"):
        op.execute(
            sa.text(
                """
                UPDATE collections AS c
                SET data_instance_id = ti.id
                FROM tool_instances AS ti
                WHERE c.data_instance_id IS NULL
                  AND c.config IS NOT NULL
                  AND (c.config -> 'bindings' -> 0 ->> 'instance_id') ~* '^[0-9a-f-]{36}$'
                  AND ti.id = ((c.config -> 'bindings' -> 0 ->> 'instance_id')::uuid)
                  AND ti.instance_kind = 'data'
                """
            )
        )

    bind = op.get_bind()
    unresolved = bind.execute(
        sa.text(
            "SELECT id::text FROM collections WHERE data_instance_id IS NULL ORDER BY created_at ASC"
        )
    ).fetchall()
    if unresolved:
        unresolved_ids = ", ".join(row[0] for row in unresolved[:20])
        raise RuntimeError(
            "Migration 0014 failed: unresolved collections without data_instance_id: "
            f"{unresolved_ids}"
        )

    op.alter_column("collections", "data_instance_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)

    if _column_exists("collections", "config"):
        op.execute(
            sa.text(
                """
                UPDATE collections
                SET config = config - 'bindings'
                WHERE config ? 'bindings'
                """
            )
        )


def downgrade() -> None:
    fk_name = "fk_collections_data_instance_id_tool_instances"

    op.alter_column("collections", "data_instance_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)

    if _column_exists("collections", "config"):
        op.execute(
            sa.text(
                """
                UPDATE collections
                SET config = COALESCE(config, '{}'::jsonb)
                             || jsonb_build_object(
                                  'bindings',
                                  jsonb_build_array(
                                      jsonb_build_object('instance_id', data_instance_id::text)
                                  )
                                )
                WHERE data_instance_id IS NOT NULL
                """
            )
        )

    if _fk_exists("collections", fk_name):
        op.drop_constraint(fk_name, "collections", type_="foreignkey")
