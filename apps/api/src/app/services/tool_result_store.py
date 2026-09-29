"""Service for complete, run-scoped tool payload persistence and analysis."""
from __future__ import annotations

import json
import hashlib
from datetime import datetime, timedelta, timezone
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
    """Persist payloads and run bounded PostgreSQL JSONB analysis queries."""

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
    ) -> dict[str, Any]:
        settings = get_settings()
        try:
            serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str)
        except (TypeError, ValueError) as exc:
            raise ToolResultStoreError("Tool result is not JSON serializable") from exc
        if len(serialized.encode("utf-8")) > settings.TOOL_RESULTS_MAX_PAYLOAD_BYTES:
            raise ToolResultStoreError("Tool result exceeds the configured storage limit")
        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.TOOL_RESULTS_RETENTION_DAYS)
        statement = text("""
            INSERT INTO runtime_tool_payloads
                (run_id, call_id, operation, tenant_id, user_id, task_id,
                 agent_execution_id, payload, payload_sha256, source_total,
                 source_complete, created_at, expires_at)
            VALUES
                (:run_id, :call_id, :operation, :tenant_id, :user_id, :task_id,
                 :agent_execution_id, CAST(:payload AS jsonb), :payload_sha256,
                 :source_total, :source_complete, now(), :expires_at)
            ON CONFLICT (run_id, call_id) DO UPDATE SET
                payload = EXCLUDED.payload,
                payload_sha256 = EXCLUDED.payload_sha256,
                source_total = EXCLUDED.source_total,
                source_complete = EXCLUDED.source_complete,
                expires_at = EXCLUDED.expires_at
            RETURNING id::text AS result_id
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
                    "source_complete": _source_complete(payload),
                    "expires_at": expires_at,
                })).mappings().one()
                fields = []
                if isinstance(payload, dict):
                    fields = [{"path": str(key)[:128], "type": _json_type(value),
                               "item_count": len(value) if isinstance(value, list) else None}
                              for key, value in list(payload.items())[:30]]
                return {
                    "result_id": row["result_id"],
                    "payload_chars": len(serialized),
                    "payload_type": _json_type(payload),
                    "fields": fields,
                    "source_total": _source_total(payload),
                    "source_complete": _source_complete(payload),
                    "inline_complete": len(serialized) <= settings.TOOL_RESULTS_INLINE_CONTEXT_CHARS,
                }
        except Exception as exc:
            raise ToolResultStoreError("Could not persist tool result") from exc

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
        equals: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> dict[str, Any]:
        if mode == "project" and not paths:
            raise ToolResultStoreError("paths is required for project")
        if mode == "text" and not text_path:
            raise ToolResultStoreError("text_path is required for text")
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
        safe_limit = max(1, min(int(limit), 50))
        safe_offset = max(0, min(int(offset), 100000))
        if mode == "select":
            return await self._select(
                result_id, run_id, tenant_id, user_id, array_path, fields or [],
                filter_path, equals, safe_offset, safe_limit,
            )
        if mode == "aggregate":
            return await self._aggregate(
                result_id, run_id, tenant_id, user_id, array_path, group_by,
                filter_path, equals,
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
                      array_path: str, fields: list[str], filter_path: str, equals: str | None,
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
              AND (:equals IS NULL OR e.value #>> CAST(:filter_path AS text[]) = :equals)
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
              AND (:equals IS NULL OR e.value #>> CAST(:filter_path AS text[]) = :equals)
            ORDER BY e.ordinality OFFSET :offset LIMIT :limit
        """)
        args = {"result_id": result_id, "run_id": run_id, "tenant_id": tenant_id,
                "user_id": user_id, "array_path": path,
                "filter_path": filter_segments or [""], "equals": equals}
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
                         array_path: str, group_by: str, filter_path: str, equals: str | None) -> dict[str, Any]:
        path = _path_segments(array_path)
        group_segments = _path_segments(group_by) if group_by else []
        filter_segments = _path_segments(filter_path) if filter_path else [""]
        if group_segments:
            statement = text("""
                SELECT e.value #>> CAST(:group_path AS text[]) AS group_value,
                       count(*) AS count, count(*) OVER() AS group_total
                FROM runtime_tool_payloads p,
                     LATERAL jsonb_array_elements(CASE
                         WHEN jsonb_typeof(p.payload #> CAST(:array_path AS text[])) = 'array'
                         THEN p.payload #> CAST(:array_path AS text[]) ELSE '[]'::jsonb END) AS e(value)
                WHERE p.id = CAST(:result_id AS uuid) AND p.run_id = :run_id
                  AND p.tenant_id = :tenant_id AND p.user_id = :user_id
                  AND (:equals IS NULL OR e.value #>> CAST(:filter_path AS text[]) = :equals)
                GROUP BY group_value ORDER BY count DESC LIMIT 50
            """)
            async with get_tool_results_engine().connect() as connection:
                rows = (await connection.execute(statement, {
                    "result_id": result_id, "run_id": run_id, "tenant_id": tenant_id,
                    "user_id": user_id, "array_path": path, "group_path": group_segments,
                    "filter_path": filter_segments, "equals": equals,
                })).mappings().all()
            total_groups = int(rows[0]["group_total"]) if rows else 0
            projected_groups = []
            used = 0
            size_limit = _response_value_budget()
            for row in rows:
                group = {"value": str(row["group_value"] or "")[:256], "count": int(row["count"])}
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
              AND (:equals IS NULL OR e.value #>> CAST(:filter_path AS text[]) = :equals)
        """)
        async with get_tool_results_engine().connect() as connection:
            count = int((await connection.execute(count_statement, {
                "result_id": result_id, "run_id": run_id, "tenant_id": tenant_id,
                "user_id": user_id, "array_path": path,
                "filter_path": filter_segments, "equals": equals,
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


def _contains_array(value: Any) -> bool:
    if isinstance(value, list):
        return True
    if isinstance(value, dict):
        return any(_contains_array(item) for item in value.values())
    return False


def _source_total(payload: Any) -> int | None:
    if isinstance(payload, dict) and isinstance(payload.get("total"), int):
        return int(payload["total"])
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


def _source_complete(payload: Any) -> bool:
    """Detect incomplete pages, including Jira pages nested inside one issue."""
    if isinstance(payload, dict):
        total = payload.get("total")
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
        if payload.get("isLast") is False or payload.get("nextPage"):
            return False
        return all(_source_complete(value) for value in payload.values())
    if isinstance(payload, list):
        return all(_source_complete(value) for value in payload)
    return True
