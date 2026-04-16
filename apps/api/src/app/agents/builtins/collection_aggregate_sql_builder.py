from __future__ import annotations

from typing import Dict, List, Optional


class CollectionAggregateSQLBuilder:
    """Build SQL for collection aggregate tool from validated inputs."""

    def __init__(
        self,
        *,
        max_result_groups: int,
        allowed_functions: set[str],
    ) -> None:
        self.max_result_groups = int(max_result_groups)
        self.allowed_functions = set(allowed_functions)

    def build_aggregate_sql(
        self,
        collection,
        metrics: List[Dict],
        group_by: List[str],
        filters: Dict,
        time_bucket: Optional[Dict],
        having: Optional[List[Dict]] = None,
        order_by: Optional[str] = None,
    ) -> tuple[str, Dict]:
        table_name = collection.table_name
        params: Dict[str, object] = {}
        param_idx = 0

        select_parts: List[str] = []

        for field in group_by:
            select_parts.append(field)

        if time_bucket:
            tb_field = time_bucket.get("field")
            tb_interval = time_bucket.get("interval", "day")

            interval_map = {
                "hour": "hour",
                "day": "day",
                "week": "week",
                "month": "month",
                "year": "year",
            }
            pg_interval = interval_map.get(tb_interval, "day")
            select_parts.append(f"date_trunc('{pg_interval}', {tb_field}) as time_bucket")

            if tb_field not in group_by:
                group_by = group_by + [f"date_trunc('{pg_interval}', {tb_field})"]

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

        where_parts, params, param_idx = self.build_where_clause(filters, params, param_idx)
        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        group_clause = ""
        if group_by:
            group_clause = f"GROUP BY {', '.join(group_by)}"

        having_clause = ""
        if having and group_by:
            having_parts, params, param_idx = self.build_having_clause(having, params, param_idx)
            if having_parts:
                having_clause = f"HAVING {' AND '.join(having_parts)}"

        order_clause = ""
        if order_by:
            desc = order_by.startswith("-")
            order_field = order_by.lstrip("-")
            direction = "DESC" if desc else "ASC"
            order_clause = f"ORDER BY {order_field} {direction}"
        elif group_by:
            order_clause = f"ORDER BY {group_by[0]}"

        sql = f"""
            SELECT {select_clause}
            FROM {table_name}
            {where_clause}
            {group_clause}
            {having_clause}
            {order_clause}
            LIMIT {self.max_result_groups}
        """

        return sql.strip(), params

    def build_where_clause(
        self,
        filters: Dict,
        params: Dict,
        param_idx: int,
    ) -> tuple[List[str], Dict, int]:
        where_parts: List[str] = []

        if not filters:
            return where_parts, params, param_idx

        and_conditions = filters.get("and", [])
        for cond in and_conditions:
            part, params, param_idx = self.build_condition(cond, params, param_idx)
            if part:
                where_parts.append(part)

        or_conditions = filters.get("or", [])
        if or_conditions:
            or_parts = []
            for cond in or_conditions:
                part, params, param_idx = self.build_condition(cond, params, param_idx)
                if part:
                    or_parts.append(part)
            if or_parts:
                where_parts.append(f"({' OR '.join(or_parts)})")

        for key, value in filters.items():
            if key not in ("and", "or"):
                param_name = f"p{param_idx}"
                param_idx += 1
                params[param_name] = value
                where_parts.append(f"{key} = :{param_name}")

        return where_parts, params, param_idx

    def build_condition(
        self,
        cond: Dict,
        params: Dict,
        param_idx: int,
    ) -> tuple[str, Dict, int]:
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
        if op == "neq":
            params[param_name] = value
            return f"{field} != :{param_name}", params, param_idx
        if op in {"in", "not_in"}:
            values = value if isinstance(value, list) else [value]
            if not values:
                return "", params, param_idx
            placeholders = []
            for idx, item in enumerate(values):
                item_param = f"{param_name}_{idx}"
                params[item_param] = item
                placeholders.append(f":{item_param}")
            op_token = "IN" if op == "in" else "NOT IN"
            return f"{field} {op_token} ({', '.join(placeholders)})", params, param_idx
        if op == "gt":
            params[param_name] = value
            return f"{field} > :{param_name}", params, param_idx
        if op == "gte":
            params[param_name] = value
            return f"{field} >= :{param_name}", params, param_idx
        if op == "lt":
            params[param_name] = value
            return f"{field} < :{param_name}", params, param_idx
        if op == "lte":
            params[param_name] = value
            return f"{field} <= :{param_name}", params, param_idx
        if op == "range":
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
        if op in {"like", "contains"}:
            params[param_name] = f"%{value}%"
            return f"{field} ILIKE :{param_name}", params, param_idx
        if op == "is_null":
            return (f"{field} IS NULL" if value else f"{field} IS NOT NULL"), params, param_idx

        return "", params, param_idx

    def build_having_clause(
        self,
        having: List[Dict],
        params: Dict,
        param_idx: int,
    ) -> tuple[List[str], Dict, int]:
        parts: List[str] = []

        op_map = {
            "eq": "=",
            "neq": "!=",
            "gt": ">",
            "gte": ">=",
            "lt": "<",
            "lte": "<=",
        }

        for cond in having:
            func = cond.get("function")
            field = cond.get("field")
            op = cond.get("op", "gt")
            value = cond.get("value")

            if func not in self.allowed_functions:
                continue

            sql_op = op_map.get(op)
            if not sql_op:
                continue

            if func == "count":
                agg_expr = f"COUNT({field})" if field else "COUNT(*)"
            elif func == "count_distinct":
                if not field:
                    continue
                agg_expr = f"COUNT(DISTINCT {field})"
            elif func == "sum":
                if not field:
                    continue
                agg_expr = f"SUM({field})"
            elif func == "avg":
                if not field:
                    continue
                agg_expr = f"AVG({field})"
            elif func == "min":
                if not field:
                    continue
                agg_expr = f"MIN({field})"
            elif func == "max":
                if not field:
                    continue
                agg_expr = f"MAX({field})"
            else:
                continue

            param_name = f"h{param_idx}"
            param_idx += 1
            params[param_name] = value
            parts.append(f"{agg_expr} {sql_op} :{param_name}")

        return parts, params, param_idx
