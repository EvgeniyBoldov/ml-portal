"""Service for complete, run-scoped tool payload persistence and analysis."""
from __future__ import annotations

import json
import hashlib
import math
import re
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings

_engine: AsyncEngine | None = None


def get_tool_results_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            get_settings().TOOL_RESULTS_DB_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


async def dispose_tool_results_engine() -> None:
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None


class ToolResultStoreError(RuntimeError):
    pass


class ToolResultStore:
    """Persist tool payloads as JSON and as run-scoped SQL rows."""

    async def save(
        self,
        *,
        run_id: str,
        call_id: str,
        operation: str,
        tenant_id: UUID,
        user_id: UUID,
        task_id: str | None,
        agent_execution_id: str | None,
        payload: Any,
        query_sql: str | None = None,
        source_result_ids: list[str] | None = None,
        source_complete: bool | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        try:
            serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        except (TypeError, ValueError) as exc:
            raise ToolResultStoreError("Tool result is not JSON serializable") from exc
        if len(serialized.encode("utf-8")) > settings.TOOL_RESULTS_MAX_PAYLOAD_BYTES:
            raise ToolResultStoreError("Tool result exceeds the configured storage limit")
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.TOOL_RESULTS_RETENTION_DAYS)
        rows = _dataset_rows(payload)
        observed_schema, sample, schema_complete, sample_complete = _profile_rows(rows)
        statement = text("""
            INSERT INTO runtime_tool_payloads
                (run_id, call_id, operation, tenant_id, user_id, task_id,
                 agent_execution_id, payload, payload_sha256, source_total,
                 source_complete, observed_schema, sample, sample_complete, schema_complete,
                 row_count, query_sql, source_result_ids, created_at, expires_at)
            VALUES
                (:run_id, :call_id, :operation, :tenant_id, :user_id, :task_id,
                 :agent_execution_id, CAST(:payload AS jsonb), :payload_sha256,
                 :source_total, :source_complete, CAST(:observed_schema AS jsonb),
                 CAST(:sample AS jsonb), :sample_complete, :schema_complete, :row_count, :query_sql,
                 CAST(:source_result_ids AS jsonb), now(), :expires_at)
            ON CONFLICT (run_id, call_id) DO UPDATE SET
                payload = EXCLUDED.payload,
                payload_sha256 = EXCLUDED.payload_sha256,
                source_total = EXCLUDED.source_total,
                source_complete = EXCLUDED.source_complete,
                observed_schema = EXCLUDED.observed_schema,
                sample = EXCLUDED.sample,
                sample_complete = EXCLUDED.sample_complete,
                schema_complete = EXCLUDED.schema_complete,
                row_count = EXCLUDED.row_count,
                query_sql = EXCLUDED.query_sql,
                source_result_ids = EXCLUDED.source_result_ids,
                expires_at = EXCLUDED.expires_at
            RETURNING id::text AS result_id, id AS result_uuid
        """)
        try:
            async with get_tool_results_engine().begin() as connection:
                row = (await connection.execute(statement, {
                    "run_id": run_id,
                    "call_id": call_id,
                    "operation": operation,
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "task_id": task_id,
                    "agent_execution_id": agent_execution_id,
                    "payload": serialized,
                    "payload_sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
                    "source_total": _source_total(payload),
                    "source_complete": _source_complete(payload) if source_complete is None else bool(source_complete),
                    "observed_schema": json.dumps(observed_schema, ensure_ascii=False),
                    "sample": json.dumps(sample, ensure_ascii=False, default=str) if sample is not None else None,
                    "sample_complete": sample_complete,
                    "schema_complete": schema_complete,
                    "row_count": len(rows),
                    "query_sql": query_sql,
                    "source_result_ids": json.dumps(source_result_ids or []),
                    "expires_at": expires_at,
                })).mappings().one()
                await connection.execute(text("DELETE FROM runtime_tool_result_rows WHERE result_id = :result_id"), {
                    "result_id": row["result_uuid"],
                })
                if rows:
                    await connection.execute(text("""
                        INSERT INTO runtime_tool_result_rows (result_id, run_id, ordinal, data)
                        VALUES (:result_id, :run_id, :ordinal, CAST(:data AS jsonb))
                    """), [
                        {"result_id": row["result_uuid"], "run_id": run_id,
                         "ordinal": ordinal, "data": json.dumps(value, ensure_ascii=False, default=str)}
                        for ordinal, value in enumerate(rows)
                    ])
                result_id = row["result_id"]
                return {
                    "result_id": result_id,
                    "sql_ref": sql_ref_for_result(result_id),
                    "payload_chars": len(serialized),
                    "payload_type": _json_type(payload),
                    "observed_schema": observed_schema,
                    "sample": sample,
                    "schema_complete": schema_complete,
                    "sample_complete": sample_complete,
                    "row_count": len(rows),
                    "source_total": _source_total(payload),
                    "source_complete": _source_complete(payload) if source_complete is None else bool(source_complete),
                    "inline_complete": len(serialized) <= settings.TOOL_RESULTS_INLINE_CONTEXT_CHARS,
                    "query_sql": query_sql,
                    "source_result_ids": source_result_ids or [],
                }
        except Exception as exc:
            raise ToolResultStoreError("Could not persist tool result") from exc

    async def list_for_run(self, *, run_id: str, tenant_id: UUID, user_id: UUID) -> list[dict[str, Any]]:
        """Return the compact SQL source catalog visible to one runtime run."""
        statement = text("""
            SELECT id::text AS result_id, operation, row_count,
                   jsonb_typeof(payload) AS payload_type,
                   source_complete, observed_schema, sample, sample_complete, schema_complete,
                   query_sql, source_result_ids
            FROM runtime_tool_payloads
            WHERE run_id = :run_id AND tenant_id = :tenant_id AND user_id = :user_id
              AND expires_at > now()
            ORDER BY created_at, id
        """)
        async with get_tool_results_engine().connect() as connection:
            rows = (await connection.execute(statement, {
                "run_id": run_id, "tenant_id": tenant_id, "user_id": user_id,
            })).mappings().all()
        return [{
            "result_id": row["result_id"],
            "sql_ref": sql_ref_for_result(row["result_id"]),
            "operation": row["operation"],
            "row_count": int(row["row_count"] or 0),
            "payload_type": row["payload_type"],
            "source_complete": bool(row["source_complete"]),
            "observed_schema": row["observed_schema"] or {},
            "sample": row["sample"],
            "schema_complete": bool(row["schema_complete"]),
            "sample_complete": bool(row["sample_complete"]),
            "query_sql": row["query_sql"],
            "source_result_ids": row["source_result_ids"] or [],
        } for row in rows]

    async def execute_sql(
        self, *, sql: str, run_id: str, tenant_id: UUID, user_id: UUID,
        call_id: str, task_id: str | None, agent_execution_id: str | None,
    ) -> dict[str, Any]:
        """Execute one SQL query over result CTEs and persist its complete output."""
        query = str(sql or "").strip()
        if query.endswith(";"):
            query = query[:-1].rstrip()
        if not query or not query.lower().startswith(("select", "with")):
            raise ToolResultStoreError("sql must be a SELECT query or a WITH query ending in SELECT")
        sources = await self.list_for_run(run_id=run_id, tenant_id=tenant_id, user_id=user_id)
        query_identifiers = _sql_identifiers(query)
        used_sources = [source for source in sources if source["sql_ref"] in query_identifiers]
        ctes: list[str] = []
        params: dict[str, Any] = {"current_run_id": run_id}
        source_ids: list[str] = []
        for index, source in enumerate(sources):
            result_id = source["result_id"]
            ref = source["sql_ref"]
            try:
                UUID(result_id)
            except (TypeError, ValueError) as exc:
                raise ToolResultStoreError("Invalid saved result identifier") from exc
            param_name = f"source_id_{index}"
            ctes.append(
                f'{ref} AS (SELECT ordinal, data::jsonb AS data FROM runtime_tool_result_rows '
                f'WHERE result_id = CAST(:{param_name} AS uuid) AND run_id = :current_run_id '
                'AND EXISTS (SELECT 1 FROM runtime_tool_payloads p WHERE p.id = '
                f'CAST(:{param_name} AS uuid) AND p.run_id = :current_run_id '
                'AND p.tenant_id = :tenant_id AND p.user_id = :user_id AND p.expires_at > now()))'
            )
            params[param_name] = result_id
            if ref in query_identifiers:
                source_ids.append(result_id)
        params.update({"tenant_id": tenant_id, "user_id": user_id})
        prefix = ("WITH " + ", ".join(ctes) + ", " if ctes else "WITH ")
        settings = get_settings()
        max_rows = 10000
        wrapped_sql = prefix + f"_agent_query AS ({query}) SELECT * FROM _agent_query LIMIT {max_rows + 1}"
        result_rows: list[dict[str, Any]] = []
        result_bytes = 0
        try:
            async with get_tool_results_engine().begin() as connection:
                await connection.execute(text("SET TRANSACTION READ ONLY"))
                timeout_ms = settings.TOOL_RESULTS_SQL_TIMEOUT_SECONDS * 1000
                await connection.execute(text(f"SET LOCAL statement_timeout = '{timeout_ms}ms'"))
                result = await connection.execute(text(wrapped_sql), params)
                for row in result.mappings():
                    item = _json_compatible(dict(row))
                    result_bytes += len(json.dumps(item, ensure_ascii=False, default=str).encode("utf-8"))
                    if len(result_rows) >= max_rows or result_bytes > settings.TOOL_RESULTS_MAX_PAYLOAD_BYTES:
                        raise ToolResultStoreError("SQL result exceeds the configured result limit")
                    result_rows.append(item)
        except ToolResultStoreError:
            raise
        except Exception as exc:
            raise ToolResultStoreError(f"SQL query failed: {str(exc).splitlines()[0][:300]}") from exc

        saved = await self.save(
            run_id=run_id, call_id=call_id, operation="result.analyze.sql",
            tenant_id=tenant_id, user_id=user_id, task_id=task_id,
            agent_execution_id=agent_execution_id, payload=result_rows,
            query_sql=query, source_result_ids=source_ids,
            source_complete=all(item["source_complete"] for item in used_sources),
        )
        saved["inline_complete"] = saved["inline_complete"] and len(result_rows) <= 25
        return {
            "mode": "sql", "result_id": saved["result_id"],
            "source_result_id": saved["result_id"], "sql_ref": saved["sql_ref"],
            "row_count": saved["row_count"], "source_complete": all(item["source_complete"] for item in used_sources),
            "source_count": len(source_ids), "source_result_ids": source_ids, "query_sql": query,
            "observed_schema": saved["observed_schema"], "sample": saved["sample"],
            "schema_complete": saved["schema_complete"],
            "rows": result_rows[:25], "inline_complete": saved["inline_complete"],
            "query_result_stored": True, "query_complete": True,
            "_stored_result": saved,
        }

    async def analyze(
        self,
        *,
        result_id: str,
        run_id: str,
        tenant_id: UUID,
        user_id: UUID,
        mode: str,
        array_path: str = "",
        fields: list[str] | None = None,
        paths: list[str] | None = None,
        text_path: str = "",
        text_offset: int = 0,
        text_limit: int = 1500,
        group_by: str = "",
        filter_path: str = "",
        equals: str | int | float | bool | None = None,
        equals_provided: bool = False,
        offset: int = 0,
        limit: int = 25,
    ) -> dict[str, Any]:
        if mode not in {"overview", "project", "text", "select", "aggregate"}:
            raise ToolResultStoreError(f"Unsupported analysis mode: {mode!r}")
        if mode == "project" and not paths:
            raise ToolResultStoreError("paths is required for project")
        if mode == "text" and not text_path:
            raise ToolResultStoreError("text_path is required for text")
        try:
            UUID(result_id)
        except (TypeError, ValueError) as exc:
            raise ToolResultStoreError("result_id must be a UUID from a successful tool result") from exc
        row = await self._authorized_row(result_id, run_id, tenant_id, user_id)
        if row is None:
            raise ToolResultStoreError("Result not found or no longer available")
        payload_type = str(row["payload_type"] or "null")
        if mode == "overview":
            return await self._overview(result_id, run_id, tenant_id, user_id, payload_type, row)
        if mode == "project":
            return await self._project(result_id, run_id, tenant_id, user_id, paths or [], row)
        if mode == "text":
            return await self._text(result_id, run_id, tenant_id, user_id,
                                    text_path, text_offset, text_limit, row)
        if not array_path:
            raise ToolResultStoreError("array_path is required for select and aggregate")
        filter_active = equals_provided or equals is not None
        if filter_path and not filter_active:
            raise ToolResultStoreError("filter_path requires equals; omit filter_path to analyze all rows")
        if filter_active and not filter_path:
            raise ToolResultStoreError("filter_path is required when equals is provided")
        if equals is not None and not isinstance(equals, (str, int, float, bool)):
            raise ToolResultStoreError("equals must be a string, number, boolean, or null")
        if isinstance(equals, float) and not math.isfinite(equals):
            raise ToolResultStoreError("equals must be a finite number")
        safe_limit = max(1, min(int(limit), 50))
        safe_offset = max(0, min(int(offset), 100000))
        if mode == "select":
            return await self._select(
                result_id, run_id, tenant_id, user_id, array_path, fields or [],
                filter_path, equals, filter_active, safe_offset, safe_limit,
            )
        if mode == "aggregate":
            return await self._aggregate(
                result_id, run_id, tenant_id, user_id, array_path, group_by,
                filter_path, equals, filter_active,
            )
        raise ToolResultStoreError("Unsupported analysis mode")

    async def _project(
        self, result_id: str, run_id: str, tenant_id: UUID, user_id: UUID,
        paths: list[str], source_row: Any,
    ) -> dict[str, Any]:
        if len(paths) > 20:
            raise ToolResultStoreError("Too many paths; select at most 20")
        segments = [(path, _path_segments(path)) for path in paths]
        if len({path for path, _ in segments}) != len(segments):
            raise ToolResultStoreError("Duplicate paths are not allowed")
        statement = text("""
            SELECT jsonb_typeof(payload #> CAST(:path AS text[])) AS value_type,
                   payload #> CAST(:path AS text[]) AS value
            FROM runtime_tool_payloads
            WHERE id = CAST(:result_id AS uuid) AND run_id = :run_id
              AND tenant_id = :tenant_id AND user_id = :user_id
              AND expires_at > now()
        """)
        values: dict[str, Any] = {}
        missing_paths: list[str] = []
        size_limit = _response_value_budget()
        used = 0
        async with get_tool_results_engine().connect() as connection:
            for path, path_segments in segments:
                item = (await connection.execute(statement, {
                    "result_id": result_id, "run_id": run_id,
                    "tenant_id": tenant_id, "user_id": user_id, "path": path_segments,
                })).mappings().first()
                if item is None:
                    raise ToolResultStoreError("Result not found or no longer available")
                value_type = item["value_type"]
                if value_type is None:
                    missing_paths.append(path)
                    continue
                value = item["value"]
                if _contains_array(value):
                    raise ToolResultStoreError(f"{path} contains an array; use select with array_path")
                size = len(json.dumps({path: value}, ensure_ascii=False, default=str))
                if used + size > size_limit:
                    raise ToolResultStoreError("Selected values exceed the response limit; choose fewer or deeper paths")
                values[path] = value
                used += size
        return {
            "result_id": result_id, "source_result_id": result_id,
            "mode": "project", "values": values,
            "missing_paths": missing_paths, "source_complete": bool(source_row["source_complete"]),
        }

    async def _text(
        self, result_id: str, run_id: str, tenant_id: UUID, user_id: UUID,
        path: str, offset: int, limit: int, source_row: Any,
    ) -> dict[str, Any]:
        path_segments = _path_segments(path)
        settings = get_settings()
        safe_offset = max(0, min(int(offset), settings.TOOL_RESULTS_MAX_PAYLOAD_BYTES))
        safe_limit = max(1, min(int(limit), 2000, _response_value_budget()))
        statement = text("""
            SELECT jsonb_typeof(payload #> CAST(:path AS text[])) AS value_type,
                   length(payload #>> CAST(:path AS text[])) AS text_length,
                   substring(payload #>> CAST(:path AS text[]) from :start for :limit) AS chunk
            FROM runtime_tool_payloads
            WHERE id = CAST(:result_id AS uuid) AND run_id = :run_id
              AND tenant_id = :tenant_id AND user_id = :user_id
              AND expires_at > now()
        """)
        async with get_tool_results_engine().connect() as connection:
            item = (await connection.execute(statement, {
                "result_id": result_id, "run_id": run_id, "tenant_id": tenant_id,
                "user_id": user_id, "path": path_segments,
                "start": safe_offset + 1, "limit": safe_limit,
            })).mappings().first()
        if item is None:
            raise ToolResultStoreError("Result not found or no longer available")
        if item["value_type"] != "string":
            raise ToolResultStoreError("text_path must reference a string")
        length = int(item["text_length"])
        chunk = str(item["chunk"] or "")
        while len(json.dumps(chunk, ensure_ascii=False)) > _response_value_budget():
            chunk = chunk[:max(1, len(chunk) // 2)]
        next_offset = safe_offset + len(chunk)
        return {
            "result_id": result_id, "source_result_id": result_id,
            "mode": "text", "text_path": path,
            "offset": safe_offset, "length": length, "chunk": chunk,
            "complete": next_offset >= length,
            "next_offset": None if next_offset >= length else next_offset,
            "source_complete": bool(source_row["source_complete"]),
        }

    async def _authorized_row(self, result_id: str, run_id: str, tenant_id: UUID, user_id: UUID):
        statement = text("""
            SELECT jsonb_typeof(payload) AS payload_type, source_total, source_complete
            FROM runtime_tool_payloads
            WHERE id = CAST(:result_id AS uuid) AND run_id = :run_id
              AND tenant_id = :tenant_id AND user_id = :user_id
              AND expires_at > now()
        """)
        async with get_tool_results_engine().connect() as connection:
            return (await connection.execute(statement, {
                "result_id": result_id, "run_id": run_id,
                "tenant_id": tenant_id, "user_id": user_id,
            })).mappings().first()

    async def _overview(self, result_id: str, run_id: str, tenant_id: UUID, user_id: UUID, payload_type: str, source_row: Any) -> dict[str, Any]:
        statement = text("""
            SELECT e.key, jsonb_typeof(e.value) AS value_type,
                   CASE WHEN jsonb_typeof(e.value) = 'array'
                        THEN jsonb_array_length(e.value) ELSE NULL END AS item_count
            FROM runtime_tool_payloads p,
                 LATERAL jsonb_each(CASE WHEN jsonb_typeof(p.payload) = 'object'
                     THEN p.payload ELSE '{}'::jsonb END) AS e
            WHERE p.id = CAST(:result_id AS uuid) AND p.run_id = :run_id
              AND p.tenant_id = :tenant_id AND p.user_id = :user_id
        """)
        async with get_tool_results_engine().connect() as connection:
            rows = (await connection.execute(statement, {
                "result_id": result_id, "run_id": run_id,
                "tenant_id": tenant_id, "user_id": user_id,
            })).mappings().all()
        projected = []
        used = 0
        size_limit = _response_value_budget()
        for item in rows:
            field = {"path": str(item["key"])[:128], "type": item["value_type"], "item_count": item["item_count"]}
            size = len(json.dumps(field, ensure_ascii=False))
            if len(projected) >= 100 or used + size > size_limit:
                break
            projected.append(field)
            used += size
        return {
            "result_id": result_id,
            "mode": "overview",
            "payload_type": payload_type,
            "source_total": source_row["source_total"],
            "source_complete": source_row["source_complete"],
            "field_count": len(rows),
            "fields_complete": len(projected) == len(rows),
            "fields": projected,
        }

    async def _select(self, result_id: str, run_id: str, tenant_id: UUID, user_id: UUID,
                      array_path: str, fields: list[str], filter_path: str,
                      equals: str | int | float | bool | None, filter_active: bool,
                      offset: int, limit: int) -> dict[str, Any]:
        path = _path_segments(array_path)
        filter_segments = _path_segments(filter_path) if filter_path else []
        count_statement = text("""
            SELECT count(*) AS total
            FROM runtime_tool_payloads p,
              LATERAL jsonb_array_elements(CASE
                  WHEN jsonb_typeof(p.payload #> CAST(:array_path AS text[])) = 'array'
                  THEN p.payload #> CAST(:array_path AS text[]) ELSE '[]'::jsonb END) AS e(value)
            WHERE p.id = CAST(:result_id AS uuid) AND p.run_id = :run_id
              AND p.tenant_id = :tenant_id AND p.user_id = :user_id
              AND jsonb_typeof(p.payload #> CAST(:array_path AS text[])) = 'array'
              AND (NOT CAST(:filter_active AS boolean) OR e.value #> CAST(:filter_path AS text[]) = CAST(:equals_json AS jsonb))
        """)
        page_statement = text("""
            SELECT e.value AS value, e.ordinality AS ordinal
            FROM runtime_tool_payloads p,
              LATERAL jsonb_array_elements(CASE
                  WHEN jsonb_typeof(p.payload #> CAST(:array_path AS text[])) = 'array'
                  THEN p.payload #> CAST(:array_path AS text[]) ELSE '[]'::jsonb END)
                    WITH ORDINALITY AS e(value, ordinality)
            WHERE p.id = CAST(:result_id AS uuid) AND p.run_id = :run_id
              AND p.tenant_id = :tenant_id AND p.user_id = :user_id
              AND (NOT CAST(:filter_active AS boolean) OR e.value #> CAST(:filter_path AS text[]) = CAST(:equals_json AS jsonb))
            ORDER BY e.ordinality OFFSET :offset LIMIT :limit
        """)
        args = {"result_id": result_id, "run_id": run_id, "tenant_id": tenant_id,
                "user_id": user_id, "array_path": path,
                "filter_path": filter_segments or [""],
                "filter_active": filter_active,
                "equals_json": json.dumps(equals, ensure_ascii=False)}
        async with get_tool_results_engine().connect() as connection:
            total = int((await connection.execute(count_statement, args)).scalar_one())
            rows = (await connection.execute(page_statement, {**args, "offset": offset, "limit": limit})).mappings().all()
        values = []
        for row in rows:
            value = row["value"]
            if fields and isinstance(value, dict):
                value = {field: _get_path(value, _path_segments(field)) for field in fields}
            values.append({"ordinal": int(row["ordinal"]) - 1, "value": value})
        size_limit = _response_value_budget()
        bounded: list[dict[str, Any]] = []
        used = 0
        for item in values:
            size = len(json.dumps(item, ensure_ascii=False, default=str))
            if used + size > size_limit:
                if not bounded:
                    raise ToolResultStoreError("Selected row exceeds the response limit; choose fewer fields")
                break
            bounded.append(item)
            used += size
        returned = len(bounded)
        next_offset = offset + returned
        return {"result_id": result_id, "source_result_id": result_id, "mode": "select", "matched_count": total,
                "returned_count": returned, "source_complete": await self._source_is_complete(result_id, run_id, tenant_id, user_id),
                "selection_id": hashlib.sha256(json.dumps([path, fields, filter_segments, equals], separators=(",", ":")).encode()).hexdigest()[:20],
                "offset": offset, "complete": next_offset >= total,
                "next_offset": None if next_offset >= total else next_offset,
                "rows": bounded}

    async def _aggregate(self, result_id: str, run_id: str, tenant_id: UUID, user_id: UUID,
                         array_path: str, group_by: str, filter_path: str,
                         equals: str | int | float | bool | None, filter_active: bool) -> dict[str, Any]:
        path = _path_segments(array_path)
        group_segments = _path_segments(group_by) if group_by else []
        filter_segments = _path_segments(filter_path) if filter_path else [""]
        if group_segments:
            statement = text("""
                SELECT e.value #> CAST(:group_path AS text[]) AS group_value,
                       count(*) AS count, count(*) OVER() AS group_total
                FROM runtime_tool_payloads p,
                     LATERAL jsonb_array_elements(CASE
                         WHEN jsonb_typeof(p.payload #> CAST(:array_path AS text[])) = 'array'
                         THEN p.payload #> CAST(:array_path AS text[]) ELSE '[]'::jsonb END) AS e(value)
                WHERE p.id = CAST(:result_id AS uuid) AND p.run_id = :run_id
                  AND p.tenant_id = :tenant_id AND p.user_id = :user_id
                  AND (NOT CAST(:filter_active AS boolean) OR e.value #> CAST(:filter_path AS text[]) = CAST(:equals_json AS jsonb))
                GROUP BY group_value ORDER BY count DESC LIMIT 50
            """)
            async with get_tool_results_engine().connect() as connection:
                rows = (await connection.execute(statement, {
                    "result_id": result_id, "run_id": run_id, "tenant_id": tenant_id,
                    "user_id": user_id, "array_path": path, "group_path": group_segments,
                    "filter_path": filter_segments,
                    "filter_active": filter_active,
                    "equals_json": json.dumps(equals, ensure_ascii=False),
                })).mappings().all()
            total_groups = int(rows[0]["group_total"]) if rows else 0
            projected_groups = []
            used = 0
            size_limit = _response_value_budget()
            for row in rows:
                group_value = row["group_value"]
                group = {"value": group_value[:256] if isinstance(group_value, str) else group_value,
                         "count": int(row["count"])}
                size = len(json.dumps(group, ensure_ascii=False))
                if used + size > size_limit:
                    break
                projected_groups.append(group)
                used += size
            return {
                "result_id": result_id, "mode": "aggregate",
                "source_complete": await self._source_is_complete(result_id, run_id, tenant_id, user_id),
                "group_by": group_by, "group_total": total_groups,
                "groups_complete": total_groups == len(projected_groups),
                "groups": projected_groups,
            }
        count_statement = text("""
            SELECT count(*)
            FROM runtime_tool_payloads p,
                 LATERAL jsonb_array_elements(CASE
                     WHEN jsonb_typeof(p.payload #> CAST(:array_path AS text[])) = 'array'
                     THEN p.payload #> CAST(:array_path AS text[]) ELSE '[]'::jsonb END) AS e(value)
            WHERE p.id = CAST(:result_id AS uuid) AND p.run_id = :run_id
              AND p.tenant_id = :tenant_id AND p.user_id = :user_id
              AND (NOT CAST(:filter_active AS boolean) OR e.value #> CAST(:filter_path AS text[]) = CAST(:equals_json AS jsonb))
        """)
        async with get_tool_results_engine().connect() as connection:
            count = int((await connection.execute(count_statement, {
                "result_id": result_id, "run_id": run_id, "tenant_id": tenant_id,
                "user_id": user_id, "array_path": path,
                "filter_path": filter_segments,
                "filter_active": filter_active,
                "equals_json": json.dumps(equals, ensure_ascii=False),
            })).scalar_one())
        return {"result_id": result_id, "mode": "aggregate", "source_complete": await self._source_is_complete(result_id, run_id, tenant_id, user_id), "count": count}

    async def _source_is_complete(self, result_id: str, run_id: str, tenant_id: UUID, user_id: UUID) -> bool:
        statement = text("""SELECT source_complete FROM runtime_tool_payloads
            WHERE id = CAST(:result_id AS uuid) AND run_id = :run_id
              AND tenant_id = :tenant_id AND user_id = :user_id""")
        async with get_tool_results_engine().connect() as connection:
            return bool((await connection.execute(statement, {
                "result_id": result_id, "run_id": run_id,
                "tenant_id": tenant_id, "user_id": user_id,
            })).scalar_one())


def _path_segments(value: str) -> list[str]:
    segments = [segment for segment in str(value or "").strip("/.").replace("/", ".").split(".") if segment]
    if not segments or len(segments) > 12 or any(len(segment) > 128 for segment in segments):
        raise ToolResultStoreError("Invalid JSON path")
    return segments


def _get_path(value: Any, path: list[str]) -> Any:
    for segment in path:
        if isinstance(value, dict):
            value = value.get(segment)
        elif isinstance(value, list) and segment.isdigit() and int(segment) < len(value):
            value = value[int(segment)]
        else:
            return None
    return value


def _response_value_budget() -> int:
    # The agent context has a fixed 4,000-character cap; leave room for the
    # result envelope and JSON escaping even when the configured query cap is higher.
    return max(256, min(get_settings().TOOL_RESULTS_QUERY_CONTEXT_CHARS, 3000) - 1000)


def sql_ref_for_result(result_id: str) -> str:
    """Return the stable SQL identifier shown to agents for a stored result."""
    try:
        normalized = UUID(str(result_id)).hex
    except (TypeError, ValueError) as exc:
        raise ToolResultStoreError("Invalid saved result identifier") from exc
    return f"result_{normalized}"


def _dataset_rows(payload: Any) -> list[Any]:
    """Expose root arrays as rows and every other JSON value as one row."""
    return list(payload) if isinstance(payload, list) else [payload]


def _json_compatible(value: Any) -> Any:
    """Normalize common PostgreSQL scalar values before persisting query rows."""
    if isinstance(value, dict):
        return {str(key): _json_compatible(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(child) for child in value]
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return int(value)
        return float(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _profile_rows(rows: list[Any]) -> tuple[dict[str, Any], Any, bool, bool]:
    """Build bounded observed shape metadata without assuming uniform rows."""
    max_paths = 200
    max_depth = 12
    counts: dict[str, dict[str, Any]] = {}
    schema_complete = True
    sample_complete = True

    def visit(value: Any, path: str, depth: int) -> None:
        nonlocal schema_complete
        if depth > max_depth:
            schema_complete = False
            return
        key = path or "$"
        entry = counts.get(key)
        if entry is None:
            if len(counts) >= max_paths:
                schema_complete = False
                return
            entry = {"types": set(), "present": 0, "null": 0, "array_items": 0}
            counts[key] = entry
        kind = _json_type(value)
        entry["types"].add(kind)
        entry["present"] += 1
        if value is None:
            entry["null"] += 1
        elif isinstance(value, dict):
            for child_key, child in value.items():
                visit(child, f"{path}.{child_key}" if path else str(child_key), depth + 1)
        elif isinstance(value, list):
            entry["array_items"] += len(value)
            for child in value:
                visit(child, f"{path}[]" if path else "[]", depth + 1)

    for row in rows:
        visit(row, "", 0)
    schema = {
        path: {
            "types": sorted(entry["types"]),
            "present": entry["present"],
            "missing": max(0, len(rows) - entry["present"]),
            "null": entry["null"],
            **({"array_items": entry["array_items"]} if entry["array_items"] else {}),
        }
        for path, entry in counts.items()
    }
    sample_rows = rows[:3]
    sample: Any = sample_rows if len(rows) != 1 or isinstance(rows[0], (dict, list)) else rows[0]
    try:
        while len(json.dumps(sample, ensure_ascii=False, default=str)) > 1500 and sample_rows:
            sample_rows = sample_rows[:max(1, len(sample_rows) // 2)]
            sample = sample_rows if len(rows) != 1 or isinstance(rows[0], (dict, list)) else sample_rows[0]
            if len(sample_rows) == 1 and len(json.dumps(sample, ensure_ascii=False, default=str)) > 1500:
                sample = {"_truncated": True, "preview": json.dumps(sample, ensure_ascii=False, default=str)[:1400]}
                sample_complete = False
                break
    except Exception:
        sample = None
        sample_complete = False
    return schema, sample, schema_complete, sample_complete


def _contains_array(value: Any) -> bool:
    if isinstance(value, list):
        return True
    if isinstance(value, dict):
        return any(_contains_array(item) for item in value.values())
    return False


def _source_total(payload: Any) -> int | None:
    if isinstance(payload, dict):
        for key in ("total", "count"):
            value = payload.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
    return None


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return "string"


def _sql_identifiers(sql: str) -> set[str]:
    """Find source identifiers, excluding SQL literals and comments.

    These tokens select provenance from the already authorized run catalog;
    PostgreSQL still parses and executes the actual query.
    """
    result: set[str] = set()
    index = 0
    while index < len(sql):
        if sql.startswith("--", index):
            end = sql.find("\n", index + 2)
            index = len(sql) if end < 0 else end + 1
        elif sql.startswith("/*", index):
            index += 2
            depth = 1
            while index < len(sql) and depth:
                if sql.startswith("/*", index):
                    depth += 1
                    index += 2
                elif sql.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
        elif sql[index] in "'\"":
            quote = sql[index]
            escaped = quote == "'" and index > 0 and sql[index - 1] in "eE"
            index += 1
            value = ""
            while index < len(sql):
                if escaped and sql[index] == "\\":
                    index += 2
                    continue
                if sql[index] == quote:
                    if index + 1 < len(sql) and sql[index + 1] == quote:
                        value += quote
                        index += 2
                        continue
                    index += 1
                    break
                value += sql[index]
                index += 1
            if quote == '"':
                result.add(value)
        elif sql[index] == "$" and (tag := re.match(r"\$(?:[A-Za-z_]\w*)?\$", sql[index:])):
            end = sql.find(tag[0], index + len(tag[0]))
            index = len(sql) if end < 0 else end + len(tag[0])
        elif token := re.match(r"[A-Za-z_][A-Za-z_0-9$]*", sql[index:]):
            result.add(token[0].lower())
            index += len(token[0])
        else:
            index += 1
    return result


def _source_complete(payload: Any) -> bool:
    """Detect incomplete pages, including Jira pages nested inside one issue."""
    if isinstance(payload, dict):
        total = _source_total(payload)
        if isinstance(total, int) and not isinstance(total, bool):
            for key in ("issues", "comments", "worklogs", "values", "results"):
                items = payload.get(key)
                if isinstance(items, list):
                    try:
                        start_at = int(payload.get("startAt") or payload.get("start_at") or 0)
                    except (TypeError, ValueError):
                        return False
                    if start_at != 0 or total > len(items):
                        return False
        if isinstance(payload.get("results"), list) and (payload.get("next") or payload.get("previous")):
            return False
        if payload.get("isLast") is False or payload.get("nextPage"):
            return False
        return all(_source_complete(value) for value in payload.values())
    if isinstance(payload, list):
        return all(_source_complete(value) for value in payload)
    return True
