"""Tool schema tracking - schema_hash, worker_build_id, version inheritance

Revision ID: 0070_tool_schema_tracking
Revises: 0068_agent_observability
Create Date: 2026-02-06

Adds to tool_backend_releases:
- schema_hash: SHA256 от canonical JSON schemas для observability
- worker_build_id: ID билда воркера для трекинга кода в проде
- last_seen_at: когда последний раз видели при sync

Adds to tool_releases:
- expected_schema_hash: фиксируется при activate для детекта schema drift
- parent_release_id: FK для наследования мета-данных между версиями
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0070_tool_schema_tracking'
down_revision: Union[str, None] = '0068_agent_observability'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_fk(table_name: str, fk_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(fk.get("name") == fk_name for fk in inspector.get_foreign_keys(table_name))


def upgrade() -> None:
    # ToolBackendRelease — autodiscovery tracking
    if not _has_column('tool_backend_releases', 'schema_hash'):
        op.add_column('tool_backend_releases', sa.Column(
            'schema_hash', sa.String(64), nullable=True,
        ))
    if not _has_column('tool_backend_releases', 'worker_build_id'):
        op.add_column('tool_backend_releases', sa.Column(
            'worker_build_id', sa.String(100), nullable=True,
        ))
    if not _has_column('tool_backend_releases', 'last_seen_at'):
        op.add_column('tool_backend_releases', sa.Column(
            'last_seen_at', sa.DateTime(timezone=True), nullable=True,
        ))

    # ToolRelease — schema drift detection + version inheritance
    if not _has_column('tool_releases', 'expected_schema_hash'):
        op.add_column('tool_releases', sa.Column(
            'expected_schema_hash', sa.String(64), nullable=True,
        ))
    if not _has_column('tool_releases', 'parent_release_id'):
        op.add_column('tool_releases', sa.Column(
            'parent_release_id', postgresql.UUID(as_uuid=True), nullable=True,
        ))
    if not _has_fk('tool_releases', 'fk_tool_release_parent'):
        op.create_foreign_key(
            'fk_tool_release_parent',
            'tool_releases', 'tool_releases',
            ['parent_release_id'], ['id'],
            ondelete='SET NULL',
        )


def downgrade() -> None:
    if _has_fk('tool_releases', 'fk_tool_release_parent'):
        op.drop_constraint('fk_tool_release_parent', 'tool_releases', type_='foreignkey')
    if _has_column('tool_releases', 'parent_release_id'):
        op.drop_column('tool_releases', 'parent_release_id')
    if _has_column('tool_releases', 'expected_schema_hash'):
        op.drop_column('tool_releases', 'expected_schema_hash')
    if _has_column('tool_backend_releases', 'last_seen_at'):
        op.drop_column('tool_backend_releases', 'last_seen_at')
    if _has_column('tool_backend_releases', 'worker_build_id'):
        op.drop_column('tool_backend_releases', 'worker_build_id')
    if _has_column('tool_backend_releases', 'schema_hash'):
        op.drop_column('tool_backend_releases', 'schema_hash')
