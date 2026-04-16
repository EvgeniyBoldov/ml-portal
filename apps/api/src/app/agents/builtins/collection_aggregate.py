"""
Collection Aggregate Tool - агрегации и статистика по коллекциям (VersionedTool)
"""
from __future__ import annotations
from typing import Any, Dict, List, ClassVar, Optional
import uuid
import re

from app.core.logging import get_logger
from app.agents.handlers.versioned_tool import VersionedTool, tool_version, register_tool
from app.agents.context import ToolContext, ToolResult
from app.agents.builtins.collection_aggregate_sql_builder import CollectionAggregateSQLBuilder

logger = get_logger(__name__)

ALLOWED_AGGREGATE_FUNCTIONS = {"count", "count_distinct", "sum", "avg", "min", "max"}
MAX_GROUP_BY_FIELDS = 3
MAX_RESULT_GROUPS = 100
VALID_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SQL_BUILDER = CollectionAggregateSQLBuilder(
    max_result_groups=MAX_RESULT_GROUPS,
    allowed_functions=ALLOWED_AGGREGATE_FUNCTIONS,
)

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection_slug": {
            "type": "string",
            "description": "The collection to aggregate"
        },
        "metrics": {
            "type": "array",
            "description": "List of metrics to calculate",
            "items": {
                "type": "object",
                "properties": {
                    "function": {
                        "type": "string",
                        "enum": ["count", "count_distinct", "sum", "avg", "min", "max"],
                        "description": "Aggregate function"
                    },
                    "field": {
                        "type": "string",
                        "description": "Field to aggregate (not required for count)"
                    },
                    "alias": {
                        "type": "string",
                        "description": "Result alias name"
                    }
                },
                "required": ["function"]
            }
        },
        "group_by": {
            "type": "array",
            "description": "Fields to group by (max 3)",
            "items": {"type": "string"},
            "maxItems": 3
        },
        "filters": {
            "type": "object",
            "description": "Filter conditions (required for large tables)",
            "properties": {
                "and": {"type": "array"},
                "or": {"type": "array"}
            }
        },
        "time_bucket": {
            "type": "object",
            "description": "Time bucketing configuration",
            "properties": {
                "field": {"type": "string"},
                "interval": {
                    "type": "string",
                    "enum": ["hour", "day", "week", "month", "year"]
                }
            }
        },
        "having": {
            "type": "array",
            "description": (
                "HAVING conditions applied after GROUP BY. "
                "Each condition: {function, field, op, value}. "
                "Example: [{\"function\": \"count\", \"op\": \"gt\", \"value\": 5}]"
            ),
            "items": {
                "type": "object",
                "properties": {
                    "function": {
                        "type": "string",
                        "enum": ["count", "count_distinct", "sum", "avg", "min", "max"]
                    },
                    "field": {"type": "string"},
                    "op": {
                        "type": "string",
                        "enum": ["eq", "neq", "gt", "gte", "lt", "lte"],
                        "description": "Comparison operator"
                    },
                    "value": {
                        "type": "number",
                        "description": "Value to compare against"
                    }
                },
                "required": ["function", "op", "value"]
            }
        },
        "order_by": {
            "type": "string",
            "description": (
                "Order results by a metric alias or group_by field. "
                "Prefix with '-' for descending. Example: '-metric_0'"
            )
        }
    },
    "required": ["collection_slug", "metrics"]
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {"type": "object"}
        },
        "total_groups": {"type": "integer"},
        "collection": {"type": "string"}
    }
}


@register_tool
class CollectionAggregateTool(VersionedTool):
    """
    Tool для агрегаций и статистики по коллекциям.
    
    Поддерживает: count, count_distinct, sum, avg, min, max
    С группировкой по полям и time_bucket.
    """
    
    tool_slug: ClassVar[str] = "collection.aggregate"
    domains: ClassVar[list] = ["collection.table"]
    name: ClassVar[str] = "Collection Aggregate"
    description: ClassVar[str] = "Get aggregated statistics from a collection (count, sum, avg, etc.)"
    
    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Initial version with count/sum/avg/min/max, group_by, time_bucket, DSL filters",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        """
        Выполнить агрегацию по коллекции.
        """
        from sqlalchemy import text
        from app.core.db import get_session_factory
        from app.services.collection_service import CollectionService
        
        log = ctx.tool_logger("collection.aggregate")
        
        collection_slug = args.get("collection_slug")
        metrics = args.get("metrics", [])
        group_by = args.get("group_by", [])
        filters = args.get("filters", {})
        time_bucket = args.get("time_bucket")
        having = args.get("having", [])
        order_by = args.get("order_by")
        
        log.info("Starting collection aggregate",
                 collection=collection_slug,
                 metrics_count=len(metrics),
                 group_by=group_by,
                 has_time_bucket=bool(time_bucket))
        
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
                
                # Validate metrics
                if not metrics:
                    log.warning("No metrics provided")
                    return ToolResult.fail("At least one metric is required",
                                           logs=log.entries_dict())
                
                for metric in metrics:
                    func = metric.get("function")
                    if func not in ALLOWED_AGGREGATE_FUNCTIONS:
                        log.warning("Invalid aggregate function", function=func)
                        return ToolResult.fail(f"Invalid aggregate function: {func}",
                                               logs=log.entries_dict())
                    
                    # Validate field exists (except for count)
                    field = metric.get("field")
                    if func != "count" and field:
                        if not collection.get_field_by_name(field) and field != "id":
                            log.warning("Field not found", field=field)
                            return ToolResult.fail(f"Field '{field}' not found",
                                                   logs=log.entries_dict())
                    alias = metric.get("alias")
                    if alias and not self._is_safe_identifier(alias):
                        return ToolResult.fail(
                            f"Invalid metric alias: {alias}",
                            logs=log.entries_dict(),
                        )

                # Validate group_by
                if len(group_by) > MAX_GROUP_BY_FIELDS:
                    log.warning("Too many group_by fields", count=len(group_by))
                    return ToolResult.fail(
                        f"Maximum {MAX_GROUP_BY_FIELDS} group_by fields allowed",
                        logs=log.entries_dict())
                
                for field in group_by:
                    if field not in self._allowed_group_fields(collection):
                        log.warning("Group by field not found", field=field)
                        return ToolResult.fail(f"Group by field '{field}' not found",
                                               logs=log.entries_dict())

                filter_error = self._validate_filters(collection, filters)
                if filter_error:
                    return ToolResult.fail(filter_error, logs=log.entries_dict())

                time_bucket_error = self._validate_time_bucket(collection, time_bucket)
                if time_bucket_error:
                    return ToolResult.fail(time_bucket_error, logs=log.entries_dict())
                
                # Check guardrails: require filters for large tables
                if not collection.allow_unfiltered_search and not filters:
                    log.warning("Unfiltered aggregate blocked by guardrails")
                    return ToolResult.fail(
                        "Filters are required for aggregate queries on this collection. "
                        "Please specify at least one filter condition.",
                        logs=log.entries_dict(),
                    )
                
                # Validate having conditions
                for h_cond in having:
                    h_func = h_cond.get("function")
                    if h_func not in ALLOWED_AGGREGATE_FUNCTIONS:
                        return ToolResult.fail(
                            f"Invalid HAVING function: {h_func}",
                            logs=log.entries_dict(),
                        )
                    h_field = h_cond.get("field")
                    if h_field and h_field not in self._allowed_aggregate_fields(collection):
                        return ToolResult.fail(
                            f"Field '{h_field}' not found",
                            logs=log.entries_dict(),
                        )

                order_error = self._validate_order_by(collection, metrics, group_by, time_bucket, order_by)
                if order_error:
                    return ToolResult.fail(order_error, logs=log.entries_dict())

                # Build SQL
                sql, params = self._build_aggregate_sql(
                    collection, metrics, group_by, filters, time_bucket,
                    having=having, order_by=order_by,
                )
                
                log.debug("Executing aggregate SQL", table=collection.table_name)
                
                # Execute with timeout
                timeout_sql = f"SET LOCAL statement_timeout = '{collection.query_timeout_seconds}s'"
                await session.execute(text(timeout_sql))
                
                result = await session.execute(text(sql), params)
                rows = [dict(r) for r in result.mappings().all()]
                
                # Limit results
                truncated = False
                if len(rows) > MAX_RESULT_GROUPS:
                    rows = rows[:MAX_RESULT_GROUPS]
                    truncated = True
                    log.warning("Results truncated", max_groups=MAX_RESULT_GROUPS)
                
                log.info("Aggregate completed",
                         groups=len(rows), truncated=truncated)
                
                return ToolResult.ok(
                    data={
                        "results": rows,
                        "total_groups": len(rows),
                        "collection": collection.name,
                    },
                    logs=log.entries_dict(),
                )
                
        except Exception as e:
            logger.error(f"Collection aggregate failed: {e}", exc_info=True)
            log.error("Aggregate failed", error=str(e))
            return ToolResult.fail(f"Aggregate failed: {str(e)}",
                                   logs=log.entries_dict())

    def _is_safe_identifier(self, value: str) -> bool:
        return bool(value and VALID_IDENTIFIER_PATTERN.match(value))

    def _allowed_filter_fields(self, collection) -> set[str]:
        fields = {field["name"] for field in collection.get_filterable_fields()}
        fields.add("id")
        return fields

    def _allowed_group_fields(self, collection) -> set[str]:
        fields = {field["name"] for field in collection.get_business_fields()}
        fields.add("id")
        return fields

    def _allowed_aggregate_fields(self, collection) -> set[str]:
        return self._allowed_group_fields(collection)

    def _validate_filters(self, collection, filters: Dict) -> Optional[str]:
        if not filters:
            return None

        allowed_fields = self._allowed_filter_fields(collection)

        def _check_field(field: Optional[str]) -> Optional[str]:
            if not field:
                return "Filter condition missing 'field'"
            if field not in allowed_fields:
                return f"Unknown or non-filterable field '{field}' in filter"
            return None

        for cond in filters.get("and", []):
            error = _check_field(cond.get("field"))
            if error:
                return error

        for cond in filters.get("or", []):
            error = _check_field(cond.get("field"))
            if error:
                return error

        for key in filters.keys():
            if key in ("and", "or"):
                continue
            if key not in allowed_fields:
                return f"Unknown or non-filterable field '{key}' in filter"

        return None

    def _validate_time_bucket(self, collection, time_bucket: Optional[Dict]) -> Optional[str]:
        if not time_bucket:
            return None

        field = time_bucket.get("field")
        if not field:
            return "time_bucket requires field"
        field_def = collection.get_field_by_name(field)
        if not field_def:
            return f"Field '{field}' not found"
        if field_def.get("data_type") not in {"date", "datetime"}:
            return f"time_bucket field '{field}' must be date/datetime"
        return None

    def _validate_order_by(
        self,
        collection,
        metrics: List[Dict],
        group_by: List[str],
        time_bucket: Optional[Dict],
        order_by: Optional[str],
    ) -> Optional[str]:
        if not order_by:
            return None

        order_field = order_by.lstrip("-")
        metric_aliases = {
            metric.get("alias", f"metric_{idx}")
            for idx, metric in enumerate(metrics)
        }
        allowed_fields = set(group_by) | metric_aliases
        if time_bucket:
            allowed_fields.add("time_bucket")

        if order_field not in allowed_fields:
            return f"Invalid order_by field '{order_field}'"
        if not self._is_safe_identifier(order_field):
            return f"Invalid order_by field '{order_field}'"
        return None

    def _build_aggregate_sql(
        self,
        collection,
        metrics: List[Dict],
        group_by: List[str],
        filters: Dict,
        time_bucket: Optional[Dict],
        having: Optional[List[Dict]] = None,
        order_by: Optional[str] = None,
    ) -> tuple[str, Dict]:
        """Build aggregate SQL query."""
        return SQL_BUILDER.build_aggregate_sql(
            collection=collection,
            metrics=metrics,
            group_by=group_by,
            filters=filters,
            time_bucket=time_bucket,
            having=having,
            order_by=order_by,
        )

    def _build_where_clause(
        self,
        filters: Dict,
        params: Dict,
        param_idx: int
    ) -> tuple[List[str], Dict, int]:
        """Build WHERE clause from DSL filters."""
        return SQL_BUILDER.build_where_clause(filters, params, param_idx)

    def _build_condition(
        self,
        cond: Dict,
        params: Dict,
        param_idx: int
    ) -> tuple[str, Dict, int]:
        """Build a single condition from DSL."""
        return SQL_BUILDER.build_condition(cond, params, param_idx)

    def _build_having_clause(
        self,
        having: List[Dict],
        params: Dict,
        param_idx: int,
    ) -> tuple[List[str], Dict, int]:
        """Build HAVING clause from having conditions list."""
        return SQL_BUILDER.build_having_clause(having, params, param_idx)
