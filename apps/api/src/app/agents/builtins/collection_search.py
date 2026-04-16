"""
Collection Search Tool - универсальный поиск по SQL-коллекциям с DSL фильтрами (VersionedTool)
"""
from __future__ import annotations
from typing import Any, Dict, List, ClassVar, Optional
import uuid

from app.core.logging import get_logger
from app.agents.handlers.versioned_tool import VersionedTool, tool_version, register_tool
from app.agents.context import ToolContext, ToolResult
from app.models.collection import Collection, FieldType

logger = get_logger(__name__)

DEFAULT_LIMIT = 50
MAX_LIMIT = 100
MAX_OFFSET = 1000

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection_slug": {
            "type": "string",
            "description": "The collection to search in"
        },
        "query": {
            "type": "string",
            "description": "Text search query (searches in text fields with ILIKE)"
        },
        "filters": {
            "type": "object",
            "description": "Structured filter conditions using DSL",
            "properties": {
                "and": {
                    "type": "array",
                    "description": "List of conditions joined with AND",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field": {"type": "string"},
                            "op": {"type": "string", "enum": ["eq", "neq", "in", "not_in", "like", "contains", "gt", "gte", "lt", "lte", "range", "is_null"]},
                            "value": {}
                        }
                    }
                },
                "or": {
                    "type": "array",
                    "description": "List of conditions joined with OR"
                }
            }
        },
        "sort": {
            "type": "array",
            "description": "Sort order",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "order": {"type": "string", "enum": ["asc", "desc"]}
                }
            }
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of results (default: 50, max: 100)",
            "default": 50,
            "minimum": 1,
            "maximum": 100
        },
        "offset": {
            "type": "integer",
            "description": "Number of results to skip (max: 1000)",
            "default": 0,
            "minimum": 0,
            "maximum": 1000
        }
    },
    "required": ["collection_slug"]
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "rows": {
            "type": "array",
            "items": {"type": "object"}
        },
        "total": {"type": "integer"},
        "returned": {"type": "integer"},
        "collection": {"type": "string"},
        "has_more": {"type": "boolean"}
    }
}


@register_tool
class CollectionSearchTool(VersionedTool):
    """
    Tool для поиска по SQL-коллекциям с DSL фильтрами.
    
    Поддерживает:
    - Структурные фильтры через DSL (and/or условия)
    - Текстовый поиск по text полям
    - Сортировку и пагинацию
    - Guardrails (лимиты, таймауты, обязательные фильтры)
    """
    
    tool_slug: ClassVar[str] = "collection.search"
    domains: ClassVar[list] = ["collection.table"]
    name: ClassVar[str] = "Collection Search"
    description: ClassVar[str] = "Search in a data collection with filters and text search"

    @classmethod
    def build_schema_for_collection(cls, collection: Collection) -> Dict[str, Any]:
        """
        Генерирует input_schema для конкретной коллекции.
        Используется для формирования инструкций LLM.
        """
        properties = {
            "query": {
                "type": "string",
                "description": f"Free text search across text fields in '{collection.name}'"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 50)",
                "default": 50
            }
        }
        
        for field in collection.get_filterable_fields():
            field_name = field["name"]
            field_type = field["data_type"]
            field_desc = field.get("description", f"Filter by {field_name}")
            
            if field_type in {
                FieldType.INTEGER.value,
                FieldType.FLOAT.value,
                FieldType.DATETIME.value,
                FieldType.DATE.value,
            }:
                properties[f"{field_name}_from"] = {
                    "type": cls._map_field_type(field_type),
                    "description": f"{field_desc} (from/minimum)"
                }
                properties[f"{field_name}_to"] = {
                    "type": cls._map_field_type(field_type),
                    "description": f"{field_desc} (to/maximum)"
                }
            else:
                properties[field_name] = {
                    "type": cls._map_field_type(field_type),
                    "description": field_desc
                }
        
        return {
            "type": "object",
            "properties": properties,
            "required": []
        }

    @classmethod
    def _map_field_type(cls, field_type: str) -> str:
        """Map collection field type to JSON Schema type"""
        mapping = {
            "string": "string",
            "text": "string",
            "integer": "integer",
            "float": "number",
            "boolean": "boolean",
            "datetime": "string",
            "date": "string",
            "enum": "string",
            "json": "object",
        }
        return mapping.get(field_type, "string")

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Initial version with DSL filters, text search, sorting, pagination, guardrails",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        """
        Выполнить поиск по коллекции с DSL фильтрами и guardrails.
        """
        from sqlalchemy import text
        from app.core.db import get_session_factory
        from app.services.collection_service import CollectionService
        
        log = ctx.tool_logger("collection.search")
        
        collection_slug = args.get("collection_slug")
        query = args.get("query")
        filters = args.get("filters", {})
        sort = args.get("sort", [])
        # Normalize sort: if string, convert to array
        if isinstance(sort, str):
            # Parse "field desc" or "field asc"
            parts = sort.strip().split()
            if len(parts) >= 2:
                sort = [{"field": parts[0], "order": parts[1].lower()}]
            elif len(parts) == 1:
                sort = [{"field": parts[0], "order": "desc"}]
            else:
                sort = []
        elif isinstance(sort, list) and sort and isinstance(sort[0], dict):
            # Already array format, ensure order is lowercase
            for s in sort:
                if isinstance(s, dict) and "order" in s:
                    s["order"] = str(s["order"]).lower()
        try:
            limit = min(int(args.get("limit", DEFAULT_LIMIT)), MAX_LIMIT)
        except (TypeError, ValueError):
            limit = DEFAULT_LIMIT
        try:
            offset = min(int(args.get("offset", 0)), MAX_OFFSET)
        except (TypeError, ValueError):
            offset = 0
        
        log.info("Starting collection search",
                 collection=collection_slug,
                 query=query[:50] if query else None,
                 has_filters=bool(filters),
                 limit=limit, offset=offset)
        
        try:
            tenant_uuid = uuid.UUID(ctx.tenant_id) if isinstance(ctx.tenant_id, str) else ctx.tenant_id
            
            session_factory = get_session_factory()
            async with session_factory() as session:
                service = CollectionService(session)
                
                collection = await service.get_by_slug(tenant_uuid, collection_slug)
                if not collection:
                    log.error("Collection not found", collection=collection_slug)
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' not found",
                        logs=log.entries_dict(),
                    )
                
                # Apply guardrails
                effective_limit = min(limit, collection.max_limit)
                
                # Check if filters required
                has_filters = bool(filters.get("and") or filters.get("or") or query)
                if not collection.allow_unfiltered_search and not has_filters:
                    log.warning("Unfiltered search blocked by guardrails",
                                collection=collection_slug)
                    return ToolResult.fail(
                        "Filters or query are required for this collection. "
                        "Please specify at least one filter condition or search query.",
                        logs=log.entries_dict(),
                    )
                
                # Validate filters against collection schema
                validation_error = self._validate_filters(collection, filters)
                if validation_error:
                    log.warning("Filter validation failed", error=validation_error)
                    return ToolResult.fail(validation_error,
                                           logs=log.entries_dict())
                
                # Build SQL query
                sql, params = self._build_search_sql(
                    collection, filters, query, sort, effective_limit, offset
                )
                
                log.debug("Executing SQL query", table=collection.table_name)
                
                # Execute with timeout
                timeout_sql = f"SET LOCAL statement_timeout = '{collection.query_timeout_seconds}s'"
                await session.execute(text(timeout_sql))
                
                result = await session.execute(text(sql), params)
                rows = [dict(r) for r in result.mappings().all()]
                
                # Get total count (without limit/offset)
                count_sql, count_params = self._build_count_sql(collection, filters, query)
                count_result = await session.execute(text(count_sql), count_params)
                total = count_result.scalar() or 0
                
                formatted_rows = self._format_rows(rows, collection)
                
                log.info("Search completed",
                         returned=len(formatted_rows), total=total,
                         has_more=(offset + len(formatted_rows)) < total)
                
                return ToolResult.ok(
                    data={
                        "rows": formatted_rows,
                        "total": total,
                        "returned": len(formatted_rows),
                        "collection": collection.name,
                        "has_more": (offset + len(formatted_rows)) < total,
                    },
                    logs=log.entries_dict(),
                )
                
        except Exception as e:
            logger.error(f"Collection search failed: {e}", exc_info=True)
            log.error("Search failed", error=str(e))
            return ToolResult.fail(f"Search failed: {str(e)}",
                                   logs=log.entries_dict())

    def _validate_filters(self, collection: Collection, filters: Dict) -> Optional[str]:
        """Validate filters against collection schema"""
        if not filters:
            return None
        
        allowed_fields = {f["name"] for f in collection.get_filterable_fields()}
        allowed_fields.add("id")  # Always allow id
        
        def validate_condition(cond: Dict) -> Optional[str]:
            field = cond.get("field")
            if not field:
                return "Filter condition missing 'field'"
            if field not in allowed_fields:
                return f"Unknown field '{field}' in filter"
            return None
        
        # Validate 'and' conditions
        for cond in filters.get("and", []):
            error = validate_condition(cond)
            if error:
                return error
        
        # Validate 'or' conditions
        for cond in filters.get("or", []):
            error = validate_condition(cond)
            if error:
                return error
        
        return None

    def _build_search_sql(
        self,
        collection: Collection,
        filters: Dict,
        query: Optional[str],
        sort: List[Dict],
        limit: int,
        offset: int
    ) -> tuple[str, Dict]:
        """Build search SQL with DSL filters"""
        table_name = collection.table_name
        params = {}
        param_idx = 0
        
        # Build WHERE clause
        where_parts = []
        
        # Process DSL filters
        if filters:
            filter_parts, params, param_idx = self._build_where_from_dsl(filters, params, param_idx)
            where_parts.extend(filter_parts)
        
        # Add text search
        if query:
            text_fields = [
                f["name"]
                for f in collection.get_filterable_fields()
                if f.get("data_type") in (FieldType.STRING.value, FieldType.TEXT.value, FieldType.ENUM.value)
            ]
            if text_fields:
                text_conditions = []
                params[f"query_{param_idx}"] = f"%{query}%"
                for tf in text_fields:
                    text_conditions.append(f"{tf} ILIKE :query_{param_idx}")
                where_parts.append(f"({' OR '.join(text_conditions)})")
                param_idx += 1
        
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        
        # Build ORDER BY (validate sort fields against collection schema + system columns)
        allowed_sort_fields = {f["name"] for f in collection.get_sortable_fields()}
        allowed_sort_fields.update({"id", "_created_at", "_updated_at"})
        order_parts = []
        if sort:
            for s in sort:
                field = s.get("field")
                order = s.get("order", "asc").upper()
                if field and order in ("ASC", "DESC"):
                    # Map common LLM hallucinated field names to real columns
                    _SORT_ALIASES = {"created_at": "_created_at", "updated_at": "_updated_at"}
                    field = _SORT_ALIASES.get(field, field)
                    if field in allowed_sort_fields:
                        order_parts.append(f"{field} {order}")
                    else:
                        logger.warning(f"Sort field '{field}' not in collection schema, skipping")
        
        if not order_parts and collection.default_sort:
            ds = collection.default_sort
            order_parts.append(f"{ds.get('field', 'id')} {ds.get('order', 'desc').upper()}")
        
        order_clause = f"ORDER BY {', '.join(order_parts)}" if order_parts else ""
        
        sql = f"""
            SELECT * FROM {table_name}
            {where_clause}
            {order_clause}
            LIMIT {limit} OFFSET {offset}
        """
        
        return sql.strip(), params

    def _build_count_sql(
        self,
        collection: Collection,
        filters: Dict,
        query: Optional[str]
    ) -> tuple[str, Dict]:
        """Build count SQL"""
        table_name = collection.table_name
        params = {}
        param_idx = 0
        
        where_parts = []
        
        if filters:
            filter_parts, params, param_idx = self._build_where_from_dsl(filters, params, param_idx)
            where_parts.extend(filter_parts)
        
        if query:
            text_fields = [
                f["name"]
                for f in collection.get_filterable_fields()
                if f.get("data_type") in (FieldType.STRING.value, FieldType.TEXT.value, FieldType.ENUM.value)
            ]
            if text_fields:
                text_conditions = []
                params[f"query_{param_idx}"] = f"%{query}%"
                for tf in text_fields:
                    text_conditions.append(f"{tf} ILIKE :query_{param_idx}")
                where_parts.append(f"({' OR '.join(text_conditions)})")
        
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        
        sql = f"SELECT COUNT(*) FROM {table_name} {where_clause}"
        return sql.strip(), params

    def _build_where_from_dsl(
        self,
        filters: Dict,
        params: Dict,
        param_idx: int
    ) -> tuple[List[str], Dict, int]:
        """Build WHERE parts from DSL filters"""
        where_parts = []
        
        # Handle 'and' conditions
        for cond in filters.get("and", []):
            part, params, param_idx = self._build_condition(cond, params, param_idx)
            if part:
                where_parts.append(part)
        
        # Handle 'or' conditions
        or_conditions = filters.get("or", [])
        if or_conditions:
            or_parts = []
            for cond in or_conditions:
                part, params, param_idx = self._build_condition(cond, params, param_idx)
                if part:
                    or_parts.append(part)
            if or_parts:
                where_parts.append(f"({' OR '.join(or_parts)})")
        
        return where_parts, params, param_idx

    def _build_condition(
        self,
        cond: Dict,
        params: Dict,
        param_idx: int
    ) -> tuple[str, Dict, int]:
        """Build a single SQL condition from DSL"""
        field = cond.get("field")
        op = cond.get("op", "eq")
        value = cond.get("value")
        
        if not field:
            return "", params, param_idx
        
        param_name = f"p{param_idx}"
        param_idx += 1
        
        if op == "eq":
            params[param_name] = value
            return f"{field} = :{param_name}", params, param_idx
        elif op == "neq":
            params[param_name] = value
            return f"{field} != :{param_name}", params, param_idx
        elif op == "in":
            values = value if isinstance(value, list) else [value]
            if not values:
                return "", params, param_idx
            placeholders = []
            for idx, item in enumerate(values):
                item_param = f"{param_name}_{idx}"
                params[item_param] = item
                placeholders.append(f":{item_param}")
            return f"{field} IN ({', '.join(placeholders)})", params, param_idx
        elif op == "not_in":
            values = value if isinstance(value, list) else [value]
            if not values:
                return "", params, param_idx
            placeholders = []
            for idx, item in enumerate(values):
                item_param = f"{param_name}_{idx}"
                params[item_param] = item
                placeholders.append(f":{item_param}")
            return f"{field} NOT IN ({', '.join(placeholders)})", params, param_idx
        elif op == "gt":
            params[param_name] = value
            return f"{field} > :{param_name}", params, param_idx
        elif op == "gte":
            params[param_name] = value
            return f"{field} >= :{param_name}", params, param_idx
        elif op == "lt":
            params[param_name] = value
            return f"{field} < :{param_name}", params, param_idx
        elif op == "lte":
            params[param_name] = value
            return f"{field} <= :{param_name}", params, param_idx
        elif op == "range":
            parts = []
            if isinstance(value, dict):
                if "gte" in value:
                    params[f"{param_name}_gte"] = value["gte"]
                    parts.append(f"{field} >= :{param_name}_gte")
                if "gt" in value:
                    params[f"{param_name}_gt"] = value["gt"]
                    parts.append(f"{field} > :{param_name}_gt")
                if "lte" in value:
                    params[f"{param_name}_lte"] = value["lte"]
                    parts.append(f"{field} <= :{param_name}_lte")
                if "lt" in value:
                    params[f"{param_name}_lt"] = value["lt"]
                    parts.append(f"{field} < :{param_name}_lt")
            return f"({' AND '.join(parts)})" if parts else "", params, param_idx
        elif op == "like":
            params[param_name] = f"%{value}%"
            return f"{field} ILIKE :{param_name}", params, param_idx
        elif op == "contains":
            params[param_name] = f"%{value}%"
            return f"{field} ILIKE :{param_name}", params, param_idx
        elif op == "is_null":
            if value:
                return f"{field} IS NULL", params, param_idx
            else:
                return f"{field} IS NOT NULL", params, param_idx
        
        return "", params, param_idx

    def _format_rows(
        self,
        rows: List[Dict],
        collection: Collection
    ) -> List[Dict[str, Any]]:
        """Format rows for LLM consumption"""
        formatted = []
        
        for row in rows:
            formatted_row = {}
            
            # Always include id
            if "id" in row:
                formatted_row["id"] = str(row["id"]) if isinstance(row["id"], uuid.UUID) else row["id"]
            
            for field in collection.fields:
                field_name = field["name"]
                if field_name in row:
                    value = row[field_name]
                    if isinstance(value, uuid.UUID):
                        value = str(value)
                    if field["data_type"] == FieldType.TEXT.value and value and len(str(value)) > 500:
                        value = str(value)[:497] + "..."
                    formatted_row[field_name] = value
            formatted.append(formatted_row)
        
        return formatted


def create_collection_tool(collection: Collection) -> Dict[str, Any]:
    """
    Создаёт описание tool для конкретной коллекции.
    Используется для генерации инструкций агенту.
    """
    schema = CollectionSearchTool.build_schema_for_collection(collection)
    
    return {
        "slug": f"collection.{collection.slug}.search",
        "name": f"Search {collection.name}",
        "description": collection.description or f"Search in {collection.name} collection",
        "input_schema": schema,
    }
