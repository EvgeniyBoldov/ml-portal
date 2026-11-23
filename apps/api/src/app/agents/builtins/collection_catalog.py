"""
Collection Info Tool - schema/data-shape inspection for any collection type.
"""
from __future__ import annotations

import re
from typing import Any, ClassVar, Dict, List

from sqlalchemy import text

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.logging import get_logger
from app.models.collection import FieldType
from app.services.collection_info_service import (
    COLLECTION_INFO_FIELD_PAGE_SIZE,
    build_default_collection_info_response_builder,
)

logger = get_logger(__name__)

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection_slug": {
            "type": "string",
            "description": "The collection to inspect",
        },
        "field": {"type": "string", "minLength": 1, "description": "Inspect one exact field name and its filter hints"},
        "field_offset": {"type": "integer", "minimum": 0, "description": "Start the schema field page at this offset"},
    },
    "required": ["collection_slug"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection": {"type": "object"},
        "readiness": {"type": "object"},
        "tools": {"type": "array"},
        "contracts": {"type": "object"},
        "schema": {"type": "object"},
        "filter_hints": {"type": "object"},
        "requested_field": {"type": "string"},
        "field_offset": {"type": "integer"},
        "runtime_enrichment": {"type": "object"},
    },
}


@register_tool
class CollectionInfoTool(VersionedTool):
    """
    Inspect collection structure and metadata slice:
    - schema fields and flags
    - row-level stats (local collections)
    - top distinct values for selected dimensions
    - remote SQL catalog tables (sql collections)
    """

    tool_slug: ClassVar[str] = "collection.info"
    domains: ClassVar[list] = [
        "collection.table",
        "collection.document",
        "collection.template",
        "collection.sql",
        "collection.api",
    ]
    name: ClassVar[str] = "Collection Info"
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

        log = ctx.tool_notes("collection.info")

        collection_slug = str(args.get("collection_slug") or "").strip()
        if not collection_slug:
            return ToolResult.fail("collection_slug is required", logs=log.entries_dict())

        requested_field = str(args.get("field") or "").strip()
        limit_per_dimension = 10

        log.info(
            "Starting collection catalog inspection",
            collection=collection_slug,
            field=requested_field or None,
            limit_per_dimension=limit_per_dimension,
        )

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                service = CollectionService(session)
                collection = await service.get_by_slug(collection_slug)
                if not collection:
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' not found",
                        logs=log.entries_dict(),
                    )
                if collection_slug and str(collection.slug) != collection_slug:
                    log.error(
                        "Collection slug mismatch",
                        expected=collection_slug,
                        actual=collection.slug,
                    )
                    return ToolResult.fail(
                        f"Collection slug mismatch: expected '{collection_slug}', got '{collection.slug}'",
                        logs=log.entries_dict(),
                    )
                log.info(
                    "Resolved collection",
                    slug=collection.slug,
                    collection_type=collection.collection_type,
                )

                user_fields = [self._field_view(field) for field in collection.get_user_fields()]
                specific_fields = [self._field_view(field) for field in collection.get_specific_fields()]
                system_fields = [self._field_view(field) for field in collection.get_system_fields()]
                all_fields = [*specific_fields, *user_fields, *system_fields]
                offset = min(int(args.get("field_offset") or 0), len(all_fields))
                if requested_field:
                    fields = [field for field in all_fields if field["name"] == requested_field]
                    field_page = {"offset": 0, "total": len(fields), "shown": len(fields)}
                else:
                    fields = all_fields[offset:offset + COLLECTION_INFO_FIELD_PAGE_SIZE]
                    field_page = {"offset": offset, "total": len(all_fields), "shown": len(fields)}
                    if offset + len(fields) < len(all_fields):
                        field_page["next_offset"] = offset + len(fields)
                selected_fields = {field["name"] for field in fields}
                filterable_fields = [
                    field for field in collection.get_filterable_fields()
                    if field["name"] in selected_fields
                ]
                schema_payload = {
                    "fields": fields,
                    "field_page": field_page,
                    "user_fields": [field for field in user_fields if field["name"] in selected_fields],
                    "specific_fields": [field for field in specific_fields if field["name"] in selected_fields],
                    "system_fields": [field for field in system_fields if field["name"] in selected_fields],
                    "filterable_fields": [field["name"] for field in filterable_fields],
                    "sortable_fields": [
                        field["name"] for field in collection.get_sortable_fields()
                        if field["name"] in selected_fields
                    ],
                    "retrieval_fields": [name for name in collection.vector_fields if name in selected_fields],
                    "prompt_context_fields": [
                        field["name"] for field in collection.get_prompt_context_fields()
                        if field["name"] in selected_fields
                    ],
                }

                filter_hints_payload: Dict[str, Any] = {
                    "usage_rule": (
                        "Use these field contracts and observed values before applying filters. "
                        "Do not invent filter field names or values that are not present here."
                    ),
                    "fields": {},
                }

                if collection.table_name and self._is_safe_identifier(collection.table_name):
                    allowed_dimensions = self._resolve_allowed_dimensions(collection)
                    for field in filterable_fields:
                        field_name = str(field.get("name") or "").strip()
                        if not field_name or field_name not in allowed_dimensions or not self._is_safe_identifier(field_name):
                            continue
                        hint = await self._build_filter_hint(
                            session=session,
                            collection=collection,
                            field=field,
                            table_name=collection.table_name,
                            limit=limit_per_dimension,
                        )
                        if hint is not None:
                            filter_hints_payload["fields"][field_name] = hint

                info_builder = build_default_collection_info_response_builder()
                runtime_deps = ctx.get_runtime_deps()
                resolved_operations = info_builder.operation_resolver.resolve_for_collection(
                    runtime_deps=runtime_deps,
                    collection_slug=collection.slug,
                    collection=collection,
                )
                response_payload = await info_builder.build(
                    session=session,
                    collection=collection,
                    operations=resolved_operations,
                    inspection_payload={"schema": schema_payload, "filter_hints": filter_hints_payload},
                    selected_fields=selected_fields,
                )

                if requested_field:
                    response_payload["requested_field"] = requested_field
                else:
                    response_payload["field_offset"] = offset

                return ToolResult.ok(
                    data=response_payload,
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

    async def _build_filter_hint(
        self,
        *,
        session: Any,
        collection: Any,
        field: Dict[str, Any],
        table_name: str,
        limit: int,
    ) -> Dict[str, Any] | None:
        field_name = str(field.get("name") or "").strip()
        data_type = str(field.get("data_type") or "").strip()
        if not field_name:
            return None

        top_values = await self._collect_dimension_values(
            session=session,
            table_name=table_name,
            field_name=field_name,
            limit=limit,
        )
        distinct_count = await self._count_distinct_values(
            session=session,
            table_name=table_name,
            field_name=field_name,
        )
        coverage = "none"
        choices: List[Any] = []
        if distinct_count == 0:
            coverage = "none"
        elif distinct_count <= limit:
            coverage = "complete"
            choices = [item.get("value") for item in top_values]
        else:
            coverage = "top_values"

        operators = ["eq", "in"]
        if getattr(collection, "collection_type", None) != "document":
            operators = ["eq", "in", "see_operation_contract"]

        return {
            "field": field_name,
            "data_type": data_type,
            "filterable": bool(field.get("filterable", False)),
            "operators": operators,
            "coverage": coverage,
            "distinct_count": distinct_count,
            "choices": choices,
            "top_values": top_values,
            "notes": self._build_filter_hint_note(
                collection_type=str(getattr(collection, "collection_type", "") or "").strip(),
                field_name=field_name,
                coverage=coverage,
            ),
        }

    @staticmethod
    async def _count_distinct_values(
        *,
        session: Any,
        table_name: str,
        field_name: str,
    ) -> int:
        q = text(
            f"SELECT COUNT(DISTINCT {field_name})::bigint AS distinct_count "
            f"FROM {table_name} "
            f"WHERE {field_name} IS NOT NULL"
        )
        row = (await session.execute(q)).mappings().first() or {}
        return int(row.get("distinct_count") or 0)

    @staticmethod
    def _build_filter_hint_note(
        *,
        collection_type: str,
        field_name: str,
        coverage: str,
    ) -> str:
        if coverage == "complete":
            return (
                f"Use only values listed for '{field_name}'. "
                f"They cover all observed non-null values in this {collection_type or 'collection'}."
            )
        if coverage == "top_values":
            return (
                f"Only the most frequent observed values for '{field_name}' are shown. "
                "Do not invent values; if the needed value is missing, search/list first or refine the request."
            )
        return (
            f"No observed values are available for '{field_name}'. "
            "Do not guess values from memory."
        )

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
