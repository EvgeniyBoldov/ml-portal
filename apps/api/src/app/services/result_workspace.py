"""Run-scoped datasets: explicit pages, bounded reads and atomic append."""
from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from app.core.config import get_settings
from app.services.tool_result_protocol import ResultPage, normalize_result
from app.services.tool_result_store import (
    ToolResultStore, ToolResultStoreError, get_tool_results_engine,
    _json_dumps_exact, _profile_rows,
)


_MODEL_META_FIELDS = {
    "source", "total", "has_next", "complete", "source_tool", "start_offset",
    "coverage_incomplete", "continuation_error", "searched_types", "successful_types", "errors",
    "truncated", "columns", "input_revisions",
}


def _bounded_model_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Keep a small, stable source-status projection for model-facing calls."""
    result: dict[str, Any] = {}
    for key in _MODEL_META_FIELDS:
        if key not in meta:
            continue
        value = meta[key]
        if isinstance(value, str):
            result[key] = value[:300]
        elif isinstance(value, list):
            result[key] = [str(item)[:160] for item in value[:20]]
        elif isinstance(value, dict) and key == "input_revisions":
            result[key] = {str(name)[:64]: revision for name, revision in list(value.items())[:20]
                           if isinstance(revision, int)}
        elif value is None or isinstance(value, (bool, int, float)):
            result[key] = value
    return result


def page_key(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def normalized_page(payload: Any, source_tool: str, arguments: dict[str, Any]) -> ResultPage:
    try:
        return normalize_result(payload, source_tool, arguments)
    except (ValueError, TypeError) as exc:
        raise ToolResultStoreError(f"Source result protocol is invalid: {exc}") from exc


class ResultWorkspace:
    async def save_source(self, *, payload: Any, source_tool: str, arguments: dict[str, Any], **scope: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        page = normalized_page(payload, source_tool, arguments)
        meta = page.meta.model_dump()
        meta.update(source_tool=source_tool, start_offset=arguments.get("offset", arguments.get("start_at", 0)))
        page_bytes = len(_json_dumps_exact({"payload": payload, "meta": meta}, ensure_ascii=False, default=str).encode("utf-8"))
        if page_bytes > get_settings().TOOL_RESULTS_MAX_PAYLOAD_BYTES:
            raise ToolResultStoreError("Source page and metadata exceed the configured storage limit")
        descriptor = await ToolResultStore().save(payload=page.value, arguments=arguments,
            dataset_meta=meta, source_complete=page.meta.complete is True,
            source_page={"page_key": page_key(arguments), "payload": payload, "meta": meta,
                         "value": page.value, "source_tool": source_tool, "arguments": arguments}, **scope)
        return descriptor, {"value": page.value, "meta": {key: value for key, value in meta.items() if key != "next_arguments"}}

    async def state(self, *, result_id: str, run_id: str, tenant_id: UUID, user_id: UUID) -> dict[str, Any]:
        try:
            UUID(result_id)
        except ValueError as exc:
            raise ToolResultStoreError("result_id must be a runtime-issued UUID") from exc
        async with get_tool_results_engine().connect() as connection:
            row = (await connection.execute(text("""SELECT id::text AS result_id, call_id, operation, arguments,
                dataset_meta, revision, row_count, source_total, source_complete, observed_schema,
                schema_complete, sample, sample_complete
                FROM runtime_tool_payloads WHERE id=CAST(:result_id AS uuid) AND run_id=:run_id
                AND tenant_id=:tenant_id AND user_id=:user_id AND expires_at>now()"""),
                {"result_id": result_id, "run_id": run_id, "tenant_id": tenant_id, "user_id": user_id})).mappings().first()
        if row is None:
            raise ToolResultStoreError("Result not found or expired in this workspace")
        return dict(row)

    async def describe(self, *, offset: int = 0, limit: int = 20, query: str = "", **scope: Any) -> dict[str, Any]:
        from app.services.tool_result_store import sql_ref_for_result
        from app.services.result_sql_projection import schema_page
        if offset < 0 or not 1 <= limit <= 100:
            raise ToolResultStoreError("Invalid schema offset or limit")
        state = await self.state(**scope)
        state.pop("arguments")
        state["sql_ref"] = sql_ref_for_result(state["result_id"])
        schema = state.pop("observed_schema")
        state.pop("sample")
        state.pop("sample_complete")
        # Continuation arguments are an internal execution binding.
        state["dataset_meta"] = _bounded_model_meta(state["dataset_meta"])
        settings = get_settings()
        budget = min(settings.TOOL_RESULTS_CONTEXT_TOKENS * 3, 4000) - len(json.dumps(state, default=str).encode()) - 750
        state.update(schema_page(schema, offset=offset, limit=limit, query=query, budget=max(32, budget)))
        state["schema_hint"] = ("sql_columns are the exact top-level JSON fields of the virtual table. "
                                "Nested objects and arrays remain JSONB; use JSON operators in SQL. "
                                "There is no storage data/ordinal column. result.read fields use these same names. "
                                "query accepts comma-separated column name searches. Continue with next_schema_offset.")
        return state

    async def read(self, *, offset: int = 0, limit: int = 20, fields: list[str] | None = None,
                   revision: int | None = None, **scope: Any) -> dict[str, Any]:
        state = await self.state(**scope)
        if revision is not None and state["revision"] != revision:
            raise ToolResultStoreError("Dataset revision changed; describe it and restart reading")
        if offset < 0 or not 1 <= limit <= get_settings().TOOL_RESULTS_READ_MAX_ROWS:
            raise ToolResultStoreError("Invalid read offset or limit")
        from app.services.tool_result_store import _get_path
        from app.services.result_sql_projection import sql_columns
        columns = sql_columns(state["observed_schema"])
        field_paths: dict[str, list[str]] = {}
        for field in fields or []:
            if field in columns:
                field_paths[field] = columns[field]["path"]
            else:
                raise ToolResultStoreError(f"Unknown read field {field!r}; use result.describe for top-level column names")
        async with get_tool_results_engine().begin() as connection:
            # Lock the parent while reading so metadata and records share a revision.
            current = (await connection.execute(text("""SELECT revision FROM runtime_tool_payloads
                WHERE id=CAST(:result_id AS uuid) AND run_id=:run_id AND tenant_id=:tenant_id
                AND user_id=:user_id AND expires_at>now() FOR SHARE"""), scope)).scalar_one_or_none()
            if current != state["revision"]:
                raise ToolResultStoreError("Dataset revision changed; retry the read")
            records = (await connection.execute(text("""SELECT ordinal, data FROM runtime_tool_result_rows
                WHERE result_id=CAST(:result_id AS uuid) AND run_id=:run_id AND ordinal>=:offset
                ORDER BY ordinal LIMIT :limit"""), {**scope, "offset": offset, "limit": limit})).mappings().all()
        values = []
        budget = max(32, min(get_settings().TOOL_RESULTS_QUERY_CONTEXT_CHARS, get_settings().TOOL_RESULTS_CONTEXT_TOKENS * 3 - 1000, 3000))
        for record in records:
            value = record["data"]
            if fields:
                value = {field: _get_path(value, field_paths[field]) for field in fields}
            if len(json.dumps(values + [value], ensure_ascii=False, default=str).encode()) > budget:
                break
            values.append(value)
        next_offset = offset + len(values)
        unread = next_offset < state["row_count"]
        return {"result_id": scope["result_id"], "revision": state["revision"], "value": values,
                "returned_count": len(values), "loaded_items": state["row_count"],
                "source_complete": state["source_complete"], "read_complete": not unread,
                "next_offset": next_offset if unread and values else None,
                "record_too_large": bool(records) and not values,
                "hint": "Select fewer fields or use result.sql for oversized records." if records and not values else None}

    async def standard_query(self, *, kind: str, columns: list[str] | None = None,
                             q: str = "", offset: int = 0, limit: int = 20,
                             revision: int | None = None,
                             call_id: str, task_id: str | None, agent_execution_id: str | None,
                             **scope: Any) -> dict[str, Any]:
        from app.services.result_sql_projection import sql_columns, quote_column
        from app.services.tool_result_store import sql_ref_for_result
        state = await self.state(**scope)
        if revision is not None and revision != state["revision"]:
            raise ToolResultStoreError("Dataset revision changed; restart pagination from result.describe")
        available = sql_columns(state["observed_schema"])
        for column in columns or []:
            if column not in available:
                raise ToolResultStoreError(f"Unknown column {column!r}; use result.describe")
        if not 1 <= limit <= 100 or offset < 0:
            raise ToolResultStoreError("Invalid query offset or limit")
        ref = sql_ref_for_result(scope["result_id"])
        params: dict[str, Any] = {}
        if kind == "aggregate":
            if not columns or len(set(columns)) != len(columns):
                raise ToolResultStoreError("aggregate requires distinct grouping columns")
            group = ", ".join(quote_column(column) for column in columns)
            count_name = "count"
            while count_name in columns:
                count_name = "_" + count_name
            sql = f"SELECT {group}, count(*) AS {quote_column(count_name)} FROM {ref} GROUP BY {group} ORDER BY {quote_column(count_name)} DESC, {group}"
        elif kind == "find":
            if not q.strip():
                raise ToolResultStoreError("find requires a nonempty q")
            # Search the JSON text representation using its string escaping, so
            # quotes, backslashes and control characters still match literally.
            params["workspace_find_q"] = json.dumps(q, ensure_ascii=False)[1:-1]
            selected = ", ".join(quote_column(column) for column in columns) if columns else "*"
            sql = f"SELECT {selected} FROM {ref} AS _records WHERE strpos(lower(to_jsonb(_records)::text), lower(:workspace_find_q)) > 0 ORDER BY to_jsonb(_records)::text"
        else:
            raise ToolResultStoreError("Unknown standard query")
        sql += f" LIMIT {limit} OFFSET {offset}"
        output = await ToolResultStore().execute_sql(sql=sql, query_parameters=params, call_id=call_id,
            task_id=task_id, agent_execution_id=agent_execution_id,
            expected_revisions={scope["result_id"]: state["revision"]},
            **{key: value for key, value in scope.items() if key != "result_id"})
        output.update(operation=kind, input_result_id=scope["result_id"], offset=offset, limit=limit,
                      input_revision=state["revision"], page_may_have_more=output["row_count"] == limit)
        return output

    async def append_page(self, *, payload: Any, source_tool: str, arguments: dict[str, Any],
                          expected_revision: int, call_id: str, **scope: Any) -> dict[str, Any]:
        page = normalized_page(payload, source_tool, arguments)
        params = {**scope, "key": page_key(arguments)}
        async with get_tool_results_engine().begin() as connection:
            row = (await connection.execute(text("""SELECT payload, dataset_meta, row_count, revision
                FROM runtime_tool_payloads WHERE id=CAST(:result_id AS uuid) AND run_id=:run_id
                AND tenant_id=:tenant_id AND user_id=:user_id AND expires_at>now() FOR UPDATE"""), params)).mappings().first()
            if row is None:
                raise ToolResultStoreError("Result not found or expired")
            exists = (await connection.execute(text("""SELECT 1 FROM runtime_tool_result_pages
                WHERE result_id=CAST(:result_id AS uuid) AND page_key=:key"""), params)).scalar_one_or_none()
            if exists:
                return {"appended": False, "revision": row["revision"]}
            if row["revision"] != expected_revision:
                raise ToolResultStoreError("Dataset changed while fetching; retry continuation")
            if row["dataset_meta"].get("next_arguments") != arguments:
                raise ToolResultStoreError("Page does not match the saved continuation")
            combined = row["payload"] + page.value
            serialized = _json_dumps_exact(combined, ensure_ascii=False, default=str)
            if len(serialized.encode()) > get_settings().TOOL_RESULTS_MAX_PAYLOAD_BYTES:
                raise ToolResultStoreError("Dataset storage budget reached; saved pages remain available")
            schema, sample, schema_complete, sample_complete = _profile_rows(combined)
            meta = {**row["dataset_meta"], **page.meta.model_dump()}
            meta["coverage_incomplete"] = bool(row["dataset_meta"].get("coverage_incomplete") or meta.get("coverage_incomplete"))
            if page.meta.total is None:
                meta["total"] = row["dataset_meta"].get("total")
            if page.meta.next_arguments == arguments:
                raise ToolResultStoreError("Source continuation did not advance")
            raw_page = _json_dumps_exact({"payload": payload, "meta": page.meta.model_dump()}, default=str)
            if len(raw_page.encode("utf-8")) > get_settings().TOOL_RESULTS_MAX_PAYLOAD_BYTES:
                raise ToolResultStoreError("Source page and metadata exceed the configured storage limit")
            next_arguments = meta.get("next_arguments")
            if meta.get("has_next") and next_arguments:
                repeated_page = (await connection.execute(text("""SELECT 1 FROM runtime_tool_result_pages
                    WHERE result_id=CAST(:result_id AS uuid) AND page_key=:next_key"""),
                    {"result_id": scope["result_id"], "next_key": page_key(next_arguments)})).scalar_one_or_none()
                if repeated_page:
                    meta["has_next"] = True
                    meta["next_arguments"] = None
                    meta["coverage_incomplete"] = True
                    meta["continuation_error"] = "Source continuation cycles to an already loaded page"
            complete = (page.meta.has_next is False and row["dataset_meta"].get("start_offset", 0) == 0
                        and not meta["coverage_incomplete"]
                        and (meta["total"] is None or len(combined) >= meta["total"]))
            meta["complete"] = complete
            from app.services.result_sql_projection import sql_columns, inspect_table
            meta["table_schema"] = sql_columns(schema)
            await connection.execute(text("""INSERT INTO runtime_tool_result_pages
                (result_id,page_key,call_id,payload,meta) VALUES
                (CAST(:result_id AS uuid),:key,:call_id,CAST(:raw AS jsonb),CAST(:meta AS jsonb))"""),
                {**params, "call_id": call_id, "raw": raw_page, "meta": _json_dumps_exact(meta, default=str)})
            for start in range(0, len(page.value), 1000):
                await connection.execute(text("""INSERT INTO runtime_tool_result_rows
                    (result_id,run_id,ordinal,data) VALUES (CAST(:result_id AS uuid),:run_id,:ordinal,CAST(:data AS jsonb))"""),
                    [{"result_id": scope["result_id"], "run_id": scope["run_id"],
                      "ordinal": row["row_count"] + index, "data": _json_dumps_exact(value, default=str)}
                     for index, value in enumerate(page.value[start:start+1000], start=start)])
            await connection.execute(text("""UPDATE runtime_tool_payloads SET payload=CAST(:payload AS jsonb),
                payload_sha256=:sha, dataset_meta=CAST(:meta AS jsonb), row_count=:count,
                source_total=:total, source_complete=:complete, revision=revision+1,
                observed_schema=CAST(:schema AS jsonb), sample=CAST(:sample AS jsonb),
                schema_complete=:schema_complete, sample_complete=:sample_complete
                WHERE id=CAST(:result_id AS uuid)"""), {**params, "payload": serialized,
                "sha": hashlib.sha256(serialized.encode()).hexdigest(), "meta": _json_dumps_exact(meta, default=str),
                "count": len(combined), "total": meta["total"], "complete": complete,
                "schema": _json_dumps_exact(schema), "sample": _json_dumps_exact(sample, default=str),
                "schema_complete": schema_complete, "sample_complete": sample_complete})
            meta["table_schema"] = await inspect_table(connection, result_id=scope["result_id"], schema=schema)
            await connection.execute(text("UPDATE runtime_tool_payloads SET dataset_meta=CAST(:meta AS jsonb) WHERE id=CAST(:result_id AS uuid)"),
                {"result_id": scope["result_id"], "meta": _json_dumps_exact(meta, default=str)})
        return {"appended": True, "revision": expected_revision + 1}
