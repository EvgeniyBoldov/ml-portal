"""
Collection Aggregate Tool - агрегации и статистика по коллекциям (VersionedTool)
"""
from __future__ import annotations
from typing import Any, Dict, List, ClassVar, Optional
import uuid

from app.core.logging import get_logger
from app.agents.handlers.versioned_tool import VersionedTool, tool_version, register_tool
from app.agents.context import ToolContext, ToolResult

logger = get_logger(__name__)

ALLOWED_AGGREGATE_FUNCTIONS = {"count", "count_distinct", "sum", "avg", "min", "max"}
MAX_GROUP_BY_FIELDS = 3
MAX_RESULT_GROUPS = 100

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
    tool_group: ClassVar[str] = "collection"
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
        
        collection_slug = args.get("collection_slug")
        metrics = args.get("metrics", [])
        group_by = args.get("group_by", [])
        filters = args.get("filters", {})
        time_bucket = args.get("time_bucket")
        
        logger.info(
            f"Collection aggregate: collection={collection_slug}, "
            f"metrics={len(metrics)}, group_by={group_by}, tenant={ctx.tenant_id}"
        )
        
        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                service = CollectionService(session)
                
                collection = await service.get_by_slug(ctx.tenant_id, collection_slug)
                if not collection:
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' not found"
                    )
                
                # Validate metrics
                if not metrics:
                    return ToolResult.fail("At least one metric is required")
                
                for metric in metrics:
                    func = metric.get("function")
                    if func not in ALLOWED_AGGREGATE_FUNCTIONS:
                        return ToolResult.fail(f"Invalid aggregate function: {func}")
                    
                    # Validate field exists (except for count)
                    field = metric.get("field")
                    if func != "count" and field:
                        if not collection.get_field_by_name(field) and field != "id":
                            return ToolResult.fail(f"Field '{field}' not found")
                
                # Validate group_by
                if len(group_by) > MAX_GROUP_BY_FIELDS:
                    return ToolResult.fail(f"Maximum {MAX_GROUP_BY_FIELDS} group_by fields allowed")
                
                for field in group_by:
                    if not collection.get_field_by_name(field) and field != "id":
                        return ToolResult.fail(f"Group by field '{field}' not found")
                
                # Check guardrails: require filters for large tables
                if not collection.allow_unfiltered_search and not filters:
                    return ToolResult.fail(
                        "Filters are required for aggregate queries on this collection. "
                        "Please specify at least one filter condition."
                    )
                
                # Build SQL
                sql, params = self._build_aggregate_sql(
                    collection, metrics, group_by, filters, time_bucket
                )
                
                # Execute with timeout
                timeout_sql = f"SET LOCAL statement_timeout = '{collection.query_timeout_seconds}s'"
                await session.execute(text(timeout_sql))
                
                result = await session.execute(text(sql), params)
                rows = [dict(r) for r in result.mappings().all()]
                
                # Limit results
                if len(rows) > MAX_RESULT_GROUPS:
                    rows = rows[:MAX_RESULT_GROUPS]
                    logger.warning(f"Aggregate results truncated to {MAX_RESULT_GROUPS}")
                
                logger.info(f"Collection aggregate returned {len(rows)} groups")
                
                return ToolResult.ok(
                    data={
                        "results": rows,
                        "total_groups": len(rows),
                        "collection": collection.name,
                    }
                )
                
        except Exception as e:
            logger.error(f"Collection aggregate failed: {e}", exc_info=True)
            return ToolResult.fail(f"Aggregate failed: {str(e)}")

    def _build_aggregate_sql(
        self,
        collection,
        metrics: List[Dict],
        group_by: List[str],
        filters: Dict,
        time_bucket: Optional[Dict]
    ) -> tuple[str, Dict]:
        """Build aggregate SQL query"""
        table_name = collection.table_name
        params = {}
        param_idx = 0
        
        # Build SELECT clause
        select_parts = []
        
        # Add group_by fields to select
        for field in group_by:
            select_parts.append(field)
        
        # Add time_bucket if specified
        if time_bucket:
            tb_field = time_bucket.get("field")
            tb_interval = time_bucket.get("interval", "day")
            
            interval_map = {
                "hour": "hour",
                "day": "day",
                "week": "week",
                "month": "month",
                "year": "year"
            }
            pg_interval = interval_map.get(tb_interval, "day")
            select_parts.append(f"date_trunc('{pg_interval}', {tb_field}) as time_bucket")
            
            if tb_field not in group_by:
                group_by = group_by + [f"date_trunc('{pg_interval}', {tb_field})"]
        
        # Add metrics
        for i, metric in enumerate(metrics):
            func = metric["function"]
            field = metric.get("field")
            alias = metric.get("alias", f"metric_{i}")
            
            if func == "count":
                if field:
                    select_parts.append(f"COUNT({field}) as {alias}")
                else:
                    select_parts.append(f"COUNT(*) as {alias}")
            elif func == "count_distinct":
                select_parts.append(f"COUNT(DISTINCT {field}) as {alias}")
            elif func == "sum":
                select_parts.append(f"SUM({field}) as {alias}")
            elif func == "avg":
                select_parts.append(f"AVG({field}) as {alias}")
            elif func == "min":
                select_parts.append(f"MIN({field}) as {alias}")
            elif func == "max":
                select_parts.append(f"MAX({field}) as {alias}")
        
        select_clause = ", ".join(select_parts)
        
        # Build WHERE clause from filters
        where_parts, params, param_idx = self._build_where_clause(filters, params, param_idx)
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        
        # Build GROUP BY clause
        group_clause = ""
        if group_by:
            group_clause = f"GROUP BY {', '.join(group_by)}"
        
        # Build ORDER BY (by first group_by field or first metric)
        order_clause = ""
        if group_by:
            order_clause = f"ORDER BY {group_by[0]}"
        
        sql = f"""
            SELECT {select_clause}
            FROM {table_name}
            {where_clause}
            {group_clause}
            {order_clause}
            LIMIT {MAX_RESULT_GROUPS}
        """
        
        return sql.strip(), params

    def _build_where_clause(
        self,
        filters: Dict,
        params: Dict,
        param_idx: int
    ) -> tuple[List[str], Dict, int]:
        """Build WHERE clause from DSL filters"""
        where_parts = []
        
        if not filters:
            return where_parts, params, param_idx
        
        # Handle 'and' conditions
        and_conditions = filters.get("and", [])
        for cond in and_conditions:
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
        
        # Handle direct field conditions (legacy format)
        for key, value in filters.items():
            if key not in ("and", "or"):
                param_name = f"p{param_idx}"
                param_idx += 1
                params[param_name] = value
                where_parts.append(f"{key} = :{param_name}")
        
        return where_parts, params, param_idx

    def _build_condition(
        self,
        cond: Dict,
        params: Dict,
        param_idx: int
    ) -> tuple[str, Dict, int]:
        """Build a single condition from DSL"""
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
            params[param_name] = tuple(value) if isinstance(value, list) else (value,)
            return f"{field} IN :{param_name}", params, param_idx
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
