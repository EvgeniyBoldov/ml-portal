"""
CollectionDDL — SQL DDL builder for dynamic collection tables.

Shared component: pure functions that build DDL strings.
No database calls, no session — only string construction.
Used by CollectionService and any future migration/tooling.
"""
from __future__ import annotations

from typing import List

from sqlalchemy import text, bindparam, TextClause
from sqlalchemy.dialects.postgresql import JSONB

from app.models.collection import FieldCategory, FieldType


FIELD_TYPE_TO_PG: dict[str, str] = {
    FieldType.STRING.value: "VARCHAR(255)",
    FieldType.TEXT.value: "TEXT",
    FieldType.INTEGER.value: "BIGINT",
    FieldType.FLOAT.value: "DOUBLE PRECISION",
    FieldType.BOOLEAN.value: "BOOLEAN",
    FieldType.DATETIME.value: "TIMESTAMPTZ",
    FieldType.DATE.value: "DATE",
    FieldType.ENUM.value: "VARCHAR(100)",
    FieldType.JSON.value: "JSONB",
    FieldType.FILE.value: "JSONB",
}


def build_create_table_sql(table_name: str, fields: List[dict]) -> str:
    """Build CREATE TABLE SQL for a dynamic collection table."""
    columns = [
        "id UUID PRIMARY KEY DEFAULT gen_random_uuid()",
        "_created_at TIMESTAMPTZ DEFAULT NOW()",
        "_updated_at TIMESTAMPTZ DEFAULT NOW()",
    ]
    for field in fields:
        pg_type = FIELD_TYPE_TO_PG.get(field["data_type"], "TEXT")
        nullable = "NOT NULL" if field.get("required", False) else ""
        columns.append(f"{field['name']} {pg_type} {nullable}".strip())

    columns_sql = ",\n    ".join(columns)
    return f"CREATE TABLE IF NOT EXISTS {table_name} (\n    {columns_sql}\n)"


def build_indexes_sql(table_name: str, fields: List[dict]) -> List[str]:
    """Build structural indexes from field capabilities."""
    indexes: List[str] = []
    for field in fields:
        field_name = field["name"]
        field_type = field.get("data_type", FieldType.STRING.value)
        filterable = field.get("filterable", False)
        sortable = field.get("sortable", False)

        if filterable and field_type in (
            FieldType.STRING.value,
            FieldType.TEXT.value,
            FieldType.ENUM.value,
        ):
            indexes.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{field_name}_trgm "
                f"ON {table_name} USING gin ({field_name} gin_trgm_ops)"
            )
        elif filterable or sortable:
            indexes.append(
                f"CREATE INDEX IF NOT EXISTS idx_{table_name}_{field_name}_btree "
                f"ON {table_name} ({field_name})"
            )

    return indexes


def build_drop_indexes_sql(table_name: str, field_name: str) -> List[str]:
    """Build DROP INDEX statements for a specific field."""
    return [
        f"DROP INDEX IF EXISTS idx_{table_name}_{field_name}_trgm",
        f"DROP INDEX IF EXISTS idx_{table_name}_{field_name}_btree",
    ]


def apply_typed_binds(sql: TextClause, field_defs: List[dict]) -> TextClause:
    """Attach explicit JSONB bind types for dynamic text() queries."""
    typed_sql = sql
    for field_def in field_defs:
        if field_def.get("data_type") in (FieldType.JSON.value, FieldType.FILE.value):
            field_name = field_def["name"]
            typed_sql = typed_sql.bindparams(bindparam(field_name, type_=JSONB))
    return typed_sql


VECTOR_INFRA_ALTER_SQL = (
    "ALTER TABLE {table_name} "
    "ADD COLUMN IF NOT EXISTS _vector_status TEXT DEFAULT 'pending', "
    "ADD COLUMN IF NOT EXISTS _vector_chunk_count INTEGER DEFAULT 0, "
    "ADD COLUMN IF NOT EXISTS _vector_error TEXT"
)

VECTOR_STATUS_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_{table_name}_vector_status "
    "ON {table_name} (_vector_status)"
)
