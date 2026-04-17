"""
CollectionRowService — CRUD and search for dynamic collection table rows.

Extracted from CollectionService to isolate row-level data access from
collection lifecycle management.
"""
from __future__ import annotations

import uuid
from typing import Any, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CollectionNotFoundError, RowValidationError, AppError
from app.models.collection import Collection, FieldType, CollectionType
from app.services.collection.ddl import apply_typed_binds
from app.services.collection.field_coercion import validate_and_prepare_payload


class CollectionRowService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _require_table_name(collection: Collection) -> str:
        table_name = str(getattr(collection, "table_name", "") or "").strip()
        if not table_name:
            raise AppError("Collection storage table is not configured")
        return table_name

    # ── Reads ─────────────────────────────────────────────────────────────────

    async def get_row_by_id(
        self,
        collection: Collection,
        row_id: uuid.UUID,
    ) -> Optional[dict]:
        """Fetch a single row by UUID from the dynamic table."""
        table_name = self._require_table_name(collection)
        result = await self.session.execute(
            text(f"SELECT * FROM {table_name} WHERE id = :row_id"),
            {"row_id": row_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        return self._serialize_row(collection, dict(row))

    async def search(
        self,
        collection: Collection,
        filters: Optional[dict] = None,
        limit: int = 50,
        offset: int = 0,
        query: Optional[str] = None,
    ) -> List[dict]:
        """Search collection rows with optional filters and free-text query."""
        table_name = self._require_table_name(collection)
        where_sql, params = self._build_where(collection, filters or {}, query)

        sortable_fields = {f["name"] for f in collection.get_sortable_fields()}
        sort_column, sort_order = self._resolve_sort(collection, sortable_fields)

        sql_query = text(
            f"SELECT * FROM {table_name} "
            f"WHERE {where_sql} "
            f"ORDER BY {sort_column} {sort_order} "
            f"LIMIT :limit OFFSET :offset"
        )
        params["limit"] = limit
        params["offset"] = offset

        result = await self.session.execute(sql_query, params)
        return [
            self._serialize_row(collection, dict(row))
            for row in result.mappings().all()
        ]

    async def count(
        self,
        collection: Collection,
        filters: Optional[dict] = None,
        query: Optional[str] = None,
    ) -> int:
        """Count rows matching filters/query."""
        table_name = self._require_table_name(collection)
        where_sql, params = self._build_where(collection, filters or {}, query)
        result = await self.session.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE {where_sql}"),
            params,
        )
        return result.scalar()

    # ── Mutations ─────────────────────────────────────────────────────────────

    async def create_row(self, collection: Collection, payload: dict) -> dict:
        """Insert a new row and return its public representation."""
        table_name = self._require_table_name(collection)
        prepared = validate_and_prepare_payload(collection, payload, partial=False)
        if not prepared:
            raise RowValidationError("Row payload is empty")
        await self._ensure_sql_table_name_unique(collection, prepared)

        columns = ", ".join(prepared.keys())
        placeholders = ", ".join([f":{name}" for name in prepared.keys()])
        insert_sql = text(
            f"INSERT INTO {table_name} ({columns}) "
            f"VALUES ({placeholders}) RETURNING id"
        )
        field_defs = [f for f in collection.get_row_writable_fields() if f["name"] in prepared]
        insert_sql = apply_typed_binds(insert_sql, field_defs)

        try:
            result = await self.session.execute(insert_sql, prepared)
        except IntegrityError as exc:
            if collection.collection_type == CollectionType.SQL.value and "table_name" in prepared:
                raise RowValidationError(
                    f"Table '{str(prepared.get('table_name') or '').strip()}' is already registered in this SQL collection"
                ) from exc
            raise
        row_id = result.scalar_one()

        collection.total_rows = (collection.total_rows or 0) + 1
        await self.session.flush()

        created = await self.get_row_by_id(collection, row_id)
        if not created:
            raise AppError("Failed to load created row")
        return created

    async def update_row(
        self,
        collection: Collection,
        row_id: uuid.UUID,
        payload: dict,
    ) -> Optional[dict]:
        """Patch writable fields for a single row."""
        table_name = self._require_table_name(collection)
        prepared = validate_and_prepare_payload(collection, payload, partial=True)
        if not prepared:
            raise RowValidationError("Row payload is empty")
        await self._ensure_sql_table_name_unique(collection, prepared, row_id=row_id)

        assignments = ", ".join([f"{name} = :{name}" for name in prepared.keys()])
        update_sql = text(
            f"UPDATE {table_name} "
            f"SET {assignments}, _updated_at = NOW() "
            f"WHERE id = :row_id"
        )
        field_defs = [f for f in collection.get_row_writable_fields() if f["name"] in prepared]
        update_sql = apply_typed_binds(update_sql, field_defs)

        params = {**prepared, "row_id": row_id}
        try:
            result = await self.session.execute(update_sql, params)
        except IntegrityError as exc:
            if collection.collection_type == CollectionType.SQL.value and "table_name" in prepared:
                raise RowValidationError(
                    f"Table '{str(prepared.get('table_name') or '').strip()}' is already registered in this SQL collection"
                ) from exc
            raise
        if not result.rowcount:
            return None

        if collection.has_vector_search:
            await self.session.execute(
                text(
                    f"UPDATE {table_name} "
                    f"SET _vector_status = 'pending', "
                    f"_vector_chunk_count = 0, "
                    f"_vector_error = NULL "
                    f"WHERE id = :row_id"
                ),
                {"row_id": row_id},
            )

        await self.session.flush()
        return await self.get_row_by_id(collection, row_id)

    async def insert_rows(self, collection: Collection, rows: List[dict]) -> int:
        """Bulk insert rows into the dynamic table."""
        table_name = self._require_table_name(collection)
        if not rows:
            return 0

        field_names = [f["name"] for f in collection.get_row_writable_fields()]
        columns = ", ".join(field_names)
        placeholders = ", ".join([f":{name}" for name in field_names])
        insert_sql = text(
            f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        )
        typed_field_defs = [
            f for f in collection.get_row_writable_fields() if f["name"] in field_names
        ]
        insert_sql = apply_typed_binds(insert_sql, typed_field_defs)

        for row in rows:
            filtered_row = {name: row.get(name) for name in field_names}
            await self.session.execute(insert_sql, filtered_row)

        collection.total_rows += len(rows)
        await self.session.flush()
        return len(rows)

    async def delete_rows(
        self, collection: Collection, ids: List[uuid.UUID]
    ) -> int:
        """Delete rows by IDs and clean up Qdrant vectors if needed."""
        table_name = self._require_table_name(collection)
        if not ids:
            return 0

        placeholders = ", ".join([f":id_{i}" for i in range(len(ids))])
        params: dict[str, Any] = {f"id_{i}": id_val for i, id_val in enumerate(ids)}

        result = await self.session.execute(
            text(
                f"DELETE FROM {table_name} WHERE id IN ({placeholders})"
            ),
            params,
        )
        deleted_count = result.rowcount or 0

        collection.total_rows = max(0, collection.total_rows - deleted_count)

        if deleted_count and collection.has_vector_search and collection.qdrant_collection_name:
            from app.adapters.impl.qdrant import QdrantVectorStore

            vector_store = QdrantVectorStore()
            await vector_store.delete_by_filter(
                collection.qdrant_collection_name,
                {"row_id": [str(id_val) for id_val in ids]},
            )

            stats_result = await self.session.execute(
                text(
                    f"SELECT "
                    f"COUNT(*) FILTER (WHERE _vector_status = 'done') AS vectorized_rows, "
                    f"COUNT(*) FILTER (WHERE _vector_status = 'error') AS failed_rows, "
                    f"COALESCE(SUM(_vector_chunk_count), 0) AS total_chunks "
                    f"FROM {collection.table_name}"
                )
            )
            stats = stats_result.mappings().one()
            collection.vectorized_rows = int(stats["vectorized_rows"] or 0)
            collection.failed_rows = int(stats["failed_rows"] or 0)
            collection.total_chunks = int(stats["total_chunks"] or 0)

        await self.session.flush()
        return deleted_count

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _ensure_sql_table_name_unique(
        self,
        collection: Collection,
        payload: dict,
        *,
        row_id: uuid.UUID | None = None,
    ) -> None:
        """Enforce uniqueness of table_name for SQL collection catalog rows."""
        if collection.collection_type != CollectionType.SQL.value:
            return
        if "table_name" not in payload:
            return

        raw_value = payload.get("table_name")
        normalized = str(raw_value or "").strip()
        if not normalized:
            raise RowValidationError("Field 'table_name' is required")

        table_name = self._require_table_name(collection)
        params: dict[str, Any] = {"table_name": normalized}
        exclude_self_sql = ""
        if row_id is not None:
            params["row_id"] = row_id
            exclude_self_sql = " AND id <> :row_id"

        duplicate_result = await self.session.execute(
            text(
                f"SELECT id FROM {table_name} "
                f"WHERE lower(btrim(table_name)) = lower(btrim(:table_name))"
                f"{exclude_self_sql} "
                f"LIMIT 1"
            ),
            params,
        )
        duplicate_id = duplicate_result.scalar_one_or_none()
        if duplicate_id is not None:
            raise RowValidationError(
                f"Table '{normalized}' is already registered in this SQL collection"
            )

    @staticmethod
    def _serialize_row(collection: Collection, row: dict) -> dict:
        """Return only public (non-system) row fields."""
        business_names = [
            f["name"]
            for f in (collection.fields or [])
        ]
        visible = ["id", *business_names]
        return {name: row.get(name) for name in visible if name in row}

    @staticmethod
    def _build_where(
        collection: Collection,
        filters: dict,
        query: Optional[str],
    ) -> tuple[str, dict]:
        """Build WHERE clause and params for search/count."""
        where_clauses: List[str] = []
        params: dict = {}

        if query:
            like_clauses = []
            for field_def in collection.get_filterable_fields():
                field_name = field_def["name"]
                if field_def.get("data_type") in (
                    FieldType.STRING.value,
                    FieldType.TEXT.value,
                    FieldType.ENUM.value,
                ):
                    like_clauses.append(f"{field_name} ILIKE :query_param")
            if like_clauses:
                params["query_param"] = f"%{query}%"
                where_clauses.append(f"({' OR '.join(like_clauses)})")

        for field_def in collection.get_filterable_fields():
            field_name = field_def["name"]
            if field_name not in filters:
                continue

            value = filters[field_name]
            field_type = field_def.get("data_type")

            if field_type in (
                FieldType.INTEGER.value,
                FieldType.FLOAT.value,
                FieldType.DATETIME.value,
                FieldType.DATE.value,
            ) and isinstance(value, dict):
                if "from" in value:
                    where_clauses.append(f"{field_name} >= :p_{field_name}_from")
                    params[f"p_{field_name}_from"] = value["from"]
                if "to" in value:
                    where_clauses.append(f"{field_name} <= :p_{field_name}_to")
                    params[f"p_{field_name}_to"] = value["to"]
            elif (
                field_type in (FieldType.STRING.value, FieldType.TEXT.value, FieldType.ENUM.value)
                and isinstance(value, str)
            ):
                where_clauses.append(f"{field_name} ILIKE :p_{field_name}")
                params[f"p_{field_name}"] = f"%{value}%"
            else:
                where_clauses.append(f"{field_name} = :p_{field_name}")
                params[f"p_{field_name}"] = value

        where_sql = " AND ".join(where_clauses) if where_clauses else "TRUE"
        return where_sql, params

    @staticmethod
    def _resolve_sort(
        collection: Collection,
        sortable_fields: set[str],
    ) -> tuple[str, str]:
        """Determine ORDER BY column and direction from collection config."""
        default_sort = collection.default_sort or {}
        default_sort_field = default_sort.get("field")

        if default_sort_field in sortable_fields:
            sort_order = str(default_sort.get("order", "desc")).upper()
            if sort_order not in {"ASC", "DESC"}:
                sort_order = "DESC"
            return default_sort_field, sort_order

        if collection.time_column and collection.time_column in sortable_fields:
            return collection.time_column, "DESC"

        return "id", "DESC"
