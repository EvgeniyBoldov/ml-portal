"""
Collection Catalog Tool - schema/data-shape inspection for any collection type.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, ClassVar, Dict, List

from sqlalchemy import text

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.logging import get_logger
from app.models.collection import FieldType

logger = get_logger(__name__)

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection_slug": {
            "type": "string",
            "description": "The collection to inspect",
        },
        "dimensions": {
            "type": "array",
            "description": "Optional list of field names to return top distinct values for",
            "items": {"type": "string"},
        },
        "limit_per_dimension": {
            "type": "integer",
            "description": "Maximum number of values per dimension (default: 10, max: 50)",
            "default": 10,
            "minimum": 1,
            "maximum": 50,
        },
    },
    "required": ["collection_slug"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection": {"type": "object"},
        "schema": {"type": "object"},
        "stats": {"type": "object"},
        "dimensions": {"type": "object"},
        "remote_catalog": {"type": "object"},
    },
}


@register_tool
class CollectionCatalogTool(VersionedTool):
    """
    Inspect collection structure and metadata slice:
    - schema fields and flags
    - row-level stats (local collections)
    - top distinct values for selected dimensions
    - remote SQL catalog tables (sql collections)
    """

    tool_slug: ClassVar[str] = "collection.catalog"
    domains: ClassVar[list] = ["collection.table", "collection.document", "collection.sql", "collection.api"]
    name: ClassVar[str] = "Collection Catalog"
    description: ClassVar[str] = (
        "Inspect collection schema and data shape: fields, metadata, dimensions, and remote catalog tables."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Collection schema/data-shape inspection for table/document/sql collections",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        from app.core.db import get_session_factory
        from app.services.collection_service import CollectionService

        log = ctx.tool_logger("collection.catalog")

        collection_slug = str(args.get("collection_slug") or "").strip()
        if not collection_slug:
            return ToolResult.fail("collection_slug is required", logs=log.entries_dict())

        raw_dimensions = args.get("dimensions") or []
        dimensions = [str(item).strip() for item in raw_dimensions if str(item).strip()]
        try:
            limit_per_dimension = max(1, min(int(args.get("limit_per_dimension", 10)), 50))
        except (TypeError, ValueError):
            limit_per_dimension = 10

        log.info(
            "Starting collection catalog inspection",
            collection=collection_slug,
            dimensions=dimensions,
            limit_per_dimension=limit_per_dimension,
        )

        try:
            tenant_uuid = uuid.UUID(str(ctx.tenant_id))

            session_factory = get_session_factory()
            async with session_factory() as session:
                service = CollectionService(session)
                collection = await service.get_by_slug(tenant_uuid, collection_slug)
                if not collection:
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' not found",
                        logs=log.entries_dict(),
                    )

                schema_payload = {
                    "user_fields": [self._field_view(field) for field in collection.get_user_fields()],
                    "specific_fields": [self._field_view(field) for field in collection.get_specific_fields()],
                    "system_fields": [self._field_view(field) for field in collection.get_system_fields()],
                    "filterable_fields": [field["name"] for field in collection.get_filterable_fields()],
                    "sortable_fields": [field["name"] for field in collection.get_sortable_fields()],
                    "retrieval_fields": list(collection.vector_fields),
                    "prompt_context_fields": [field["name"] for field in collection.get_prompt_context_fields()],
                }

                stats_payload: Dict[str, Any] = {}
                dimensions_payload: Dict[str, Any] = {}

                if collection.table_name and self._is_safe_identifier(collection.table_name):
                    stats_payload = await self._collect_local_stats(session, collection.table_name)
                    if dimensions:
                        allowed_dimensions = self._resolve_allowed_dimensions(collection)
                        for dimension in dimensions:
                            if dimension not in allowed_dimensions:
                                continue
                            if not self._is_safe_identifier(dimension):
                                continue
                            values = await self._collect_dimension_values(
                                session=session,
                                table_name=collection.table_name,
                                field_name=dimension,
                                limit=limit_per_dimension,
                            )
                            dimensions_payload[dimension] = values

                remote_catalog = {
                    "tables": self._extract_remote_tables(
                        collection.table_schema if isinstance(collection.table_schema, dict) else {},
                        collection.source_contract if isinstance(collection.source_contract, dict) else {},
                    ),
                    "last_sync_at": collection.last_sync_at.isoformat() if collection.last_sync_at else None,
                }

                return ToolResult.ok(
                    data={
                        "collection": {
                            "id": str(collection.id),
                            "slug": collection.slug,
                            "name": collection.name,
                            "type": collection.collection_type,
                            "status": collection.status,
                            "table_name": collection.table_name,
                        },
                        "schema": schema_payload,
                        "stats": stats_payload,
                        "dimensions": dimensions_payload,
                        "remote_catalog": remote_catalog,
                    },
                    logs=log.entries_dict(),
                )
        except Exception as exc:
            logger.error("Collection catalog inspection failed: %s", exc, exc_info=True)
            log.error("Catalog inspection failed", error=str(exc))
            return ToolResult.fail(f"Catalog inspection failed: {exc}", logs=log.entries_dict())

    @staticmethod
    def _field_view(field: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "name": field.get("name"),
            "data_type": field.get("data_type"),
            "category": field.get("category"),
            "description": field.get("description"),
            "required": bool(field.get("required", False)),
            "filterable": bool(field.get("filterable", False)),
            "sortable": bool(field.get("sortable", False)),
            "used_in_retrieval": bool(field.get("used_in_retrieval", False)),
            "used_in_prompt_context": bool(field.get("used_in_prompt_context", False)),
        }

    @staticmethod
    def _is_safe_identifier(value: str) -> bool:
        return bool(value and _IDENTIFIER_PATTERN.match(value))

    @staticmethod
    async def _collect_local_stats(session: Any, table_name: str) -> Dict[str, Any]:
        q = text(
            f"SELECT COUNT(*)::bigint AS total_rows, "
            f"MAX(_created_at) AS last_created_at, "
            f"MAX(_updated_at) AS last_updated_at "
            f"FROM {table_name}"
        )
        row = (await session.execute(q)).mappings().first() or {}
        return {
            "total_rows": int(row.get("total_rows") or 0),
            "last_created_at": row.get("last_created_at").isoformat() if row.get("last_created_at") else None,
            "last_updated_at": row.get("last_updated_at").isoformat() if row.get("last_updated_at") else None,
        }

    async def _collect_dimension_values(
        self,
        *,
        session: Any,
        table_name: str,
        field_name: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        q = text(
            f"SELECT {field_name} AS value, COUNT(*)::bigint AS hits "
            f"FROM {table_name} "
            f"WHERE {field_name} IS NOT NULL "
            f"GROUP BY {field_name} "
            f"ORDER BY hits DESC, value ASC "
            f"LIMIT :limit"
        )
        rows = (await session.execute(q, {"limit": limit})).mappings().all()
        return [
            {"value": item.get("value"), "hits": int(item.get("hits") or 0)}
            for item in rows
        ]

    @staticmethod
    def _resolve_allowed_dimensions(collection: Any) -> set[str]:
        allowed = set()
        for field in collection.get_business_fields():
            name = str(field.get("name") or "").strip()
            data_type = str(field.get("data_type") or "").strip()
            if not name:
                continue
            if data_type in {FieldType.FILE.value, FieldType.JSON.value}:
                continue
            allowed.add(name)
        return allowed

    @staticmethod
    def _extract_remote_tables(table_schema: Dict[str, Any], source_contract: Dict[str, Any]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        seen = set()

        def _push(schema_name: str | None, table_name: str | None, columns: Any = None) -> None:
            table = str(table_name or "").strip()
            if not table:
                return
            schema = str(schema_name or "").strip() or None
            key = (schema or "", table)
            if key in seen:
                return
            seen.add(key)
            result.append(
                {
                    "schema": schema,
                    "table": table,
                    "columns_count": len(columns) if isinstance(columns, list) else None,
                }
            )

        for source in (table_schema, source_contract):
            tables = source.get("tables")
            if isinstance(tables, list):
                for item in tables:
                    if isinstance(item, str):
                        _push(None, item)
                    elif isinstance(item, dict):
                        _push(item.get("schema"), item.get("name") or item.get("table"), item.get("columns"))

            schemas = source.get("schemas")
            if isinstance(schemas, list):
                for schema_obj in schemas:
                    if not isinstance(schema_obj, dict):
                        continue
                    schema_name = schema_obj.get("schema") or schema_obj.get("name")
                    schema_tables = schema_obj.get("tables")
                    if isinstance(schema_tables, list):
                        for item in schema_tables:
                            if isinstance(item, str):
                                _push(schema_name, item)
                            elif isinstance(item, dict):
                                _push(schema_name, item.get("name") or item.get("table"), item.get("columns"))

            if isinstance(schemas, dict):
                for schema_name, schema_tables in schemas.items():
                    if isinstance(schema_tables, list):
                        for item in schema_tables:
                            if isinstance(item, str):
                                _push(schema_name, item)
                            elif isinstance(item, dict):
                                _push(schema_name, item.get("name") or item.get("table"), item.get("columns"))

        result.sort(key=lambda item: ((item.get("schema") or ""), item.get("table") or ""))
        return result
