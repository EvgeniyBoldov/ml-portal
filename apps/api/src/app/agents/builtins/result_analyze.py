"""Bounded analysis of a complete tool result from the current runtime run."""
from __future__ import annotations

import logging
from typing import Any, ClassVar, Dict
from sqlalchemy.exc import SQLAlchemyError
from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.services.tool_result_store import ToolResultStore, ToolResultStoreError

logger = logging.getLogger(__name__)

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "result_id": {"type": "string", "minLength": 1, "description": "result_id from a successful tool result in this run."},
        "mode": {"type": "string", "enum": ["overview", "select", "aggregate"], "description": "overview inspects top-level fields; select returns array rows; aggregate counts/groups array rows; project reads object paths; text pages through a string field."},
        "array_path": {"type": "string", "description": "Required for select and aggregate. Dot path to an array in the stored payload, e.g. fields.subtasks."},
        "fields": {"type": "array", "items": {"type": "string"}, "maxItems": 20, "description": "Optional dot paths projected from each selected array item."},
        "group_by": {"type": "string", "description": "Optional dot path within each array item; used by aggregate."},
        "filter_path": {"type": "string", "description": "Optional dot path within each array item to filter by equals."},
        "equals": {"type": "string", "description": "Filter value used with filter_path."},
        "offset": {"type": "integer", "minimum": 0, "description": "Row offset for select pagination."},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Maximum rows for select (1–50). Continue with next_offset until complete=true."},
    },
    "required": ["result_id", "mode"],
    "additionalProperties": False,
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "result_id": {"type": "string"}, "mode": {"type": "string"},
        "payload_type": {"type": "string"}, "fields": {"type": "array"},
        "field_count": {"type": "integer"}, "fields_complete": {"type": "boolean"},
        "rows": {"type": "array"}, "groups": {"type": "array"},
        "matched_count": {"type": "integer"}, "returned_count": {"type": "integer"},
        "count": {"type": "integer"}, "complete": {"type": "boolean"},
        "group_total": {"type": "integer"}, "groups_complete": {"type": "boolean"},
        "source_complete": {"type": "boolean"}, "next_offset": {"type": ["integer", "null"]},
        "source_result_id": {"type": "string"}, "selection_id": {"type": "string"},
        "offset": {"type": "integer"}, "source_total": {"type": ["integer", "null"]},
    },
    "required": ["result_id", "mode"],
}

_INPUT_SCHEMA_V1_1 = {
    **_INPUT_SCHEMA_V1,
    "properties": {
        **_INPUT_SCHEMA_V1["properties"],
        "equals": {"type": ["string", "number", "boolean", "null"], "description": "Filter value used with filter_path. Omit both for no filter; explicit null, empty string, false, and zero are distinct values."},
        "mode": {"type": "string", "enum": ["overview", "select", "aggregate", "project", "text"], "description": "Choose exactly one operation. select/aggregate require array_path; project requires paths; text requires text_path."},
        "paths": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "maxItems": 20, "description": "Required for project. Up to 20 dot paths to scalar/object values; paths resolving to arrays must use select."},
        "text_path": {"type": "string", "minLength": 1, "description": "Required for text. Dot path to a string field, e.g. fields.description."},
        "text_offset": {"type": "integer", "minimum": 0, "description": "Character offset for text pagination; use next_offset from the previous response."},
        "text_limit": {"type": "integer", "minimum": 1, "maximum": 2000, "description": "Maximum text characters to return (1–2000). Continue until complete=true."},
    },
}
_OUTPUT_SCHEMA_V1_1 = {
    **_OUTPUT_SCHEMA_V1,
    "properties": {
        **_OUTPUT_SCHEMA_V1["properties"],
        "values": {"type": "object", "description": "Values keyed by requested dot path; returned by project."},
        "missing_paths": {"type": "array", "items": {"type": "string"}, "description": "Requested project paths that do not exist."},
        "chunk": {"type": "string", "description": "Current bounded text page; returned by text."},
        "length": {"type": "integer", "description": "Total source string length in characters."},
        "text_path": {"type": "string", "description": "Path of the string being paged."},
        "complete": {"type": "boolean", "description": "Whether this selection or text read reached the end. For select, page using next_offset until true."},
        "next_offset": {"type": ["integer", "null"], "description": "Next row/character offset when complete is false."},
        "source_complete": {"type": "boolean", "description": "Whether the original tool result is known to contain the complete source data."},
        "rows": {"type": "array", "description": "Selected array rows; only the returned page when complete is false."},
        "groups": {"type": "array", "description": "Aggregate groups for the selected array."},
        "matched_count": {"type": "integer", "description": "Number of rows matching the filter, when available."},
        "returned_count": {"type": "integer", "description": "Number of rows in this page."},
    },
}

_INPUT_SCHEMA_V2 = {
    "type": "object",
    "properties": {
        "sql": {"type": "string", "minLength": 1, "description": "One PostgreSQL SELECT query over the result_<uuid> tables listed in the saved result catalog. JSON values are available in data."},
    },
    "required": ["sql"],
    "additionalProperties": False,
}
_OUTPUT_SCHEMA_V2 = {
    "type": "object",
    "properties": {
        "mode": {"type": "string"}, "result_id": {"type": "string"},
        "sql_ref": {"type": "string"}, "row_count": {"type": "integer"},
        "source_complete": {"type": "boolean"}, "source_count": {"type": "integer"},
        "query_sql": {"type": "string"}, "observed_schema": {"type": "object"},
        "sample": {}, "schema_complete": {"type": "boolean"},
        "rows": {"type": "array"}, "inline_complete": {"type": "boolean"},
        "query_result_stored": {"type": "boolean"},
        "query_complete": {"type": "boolean"},
        "source_result_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["mode", "result_id", "sql_ref", "row_count", "rows", "query_result_stored"],
}


@register_tool
class ResultAnalyzeTool(VersionedTool):
    tool_slug: ClassVar[str] = "result.analyze"
    domains: ClassVar[list] = ["system", "runtime"]
    name: ClassVar[str] = "Analyze Tool Result"
    description: ClassVar[str] = (
        "Query saved tool results with PostgreSQL SQL. Each saved result is available as a table named "
        "result_<uuid_without_hyphens>, with ordinal and data JSONB columns. Use the saved-result catalog "
        "for identifiers and observed JSON structure. SQL results are saved and can be queried again."
    )

    @tool_version(version="1.0.0", input_schema=_INPUT_SCHEMA_V1, output_schema=_OUTPUT_SCHEMA_V1,
                  description=(
                      "Inspect a successful result from this run. overview needs result_id; "
                      "select/aggregate also need array_path. select returns a bounded page of array rows "
                      "using fields, offset and limit; continue until complete=true. aggregate returns counts "
                      "and optional groups using group_by. This version does not support project or text modes."
                  ))
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        return await self._analyze(ctx, args)

    @tool_version(version="1.1.0", input_schema=_INPUT_SCHEMA_V1_1, output_schema=_OUTPUT_SCHEMA_V1_1,
                  description=(
                      "Inspect a successful result from this run. Pass result_id and exactly one mode: "
                      "overview; project with paths for object/scalar fields; text with text_path and optional "
                      "text_offset/text_limit; select with array_path and optional fields/offset/limit; or "
                      "aggregate with array_path and optional group_by/filter_path/equals. Paths are dot-separated. "
                      "project cannot return arrays; use select. Page select/text using next_offset until "
                      "complete=true. source_complete describes whether the original result was complete."
                  ))
    async def v1_1_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        return await self._analyze(ctx, args)

    @tool_version(version="2.0.0", input_schema=_INPUT_SCHEMA_V2, output_schema=_OUTPUT_SCHEMA_V2,
                  description=(
                      "Run one PostgreSQL SELECT query over saved tool results. Use the exact "
                      "result_<uuid_without_hyphens> table identifiers in the run result catalog; "
                      "read arbitrary nested values from data JSONB. Every query result is stored "
                      "and returned with its own sql_ref for later queries."
                  ))
    async def v2_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_notes(self.tool_slug)
        run_id = str(ctx.extra.get("runtime_root_run_id") or "").strip()
        call_id = str(ctx.extra.get("runtime_active_tool_call_id") or "").strip()
        if not run_id or not call_id:
            return ToolResult.fail("Runtime run or tool call identifier is unavailable; cannot execute saved-result SQL.", logs=log.entries_dict())
        try:
            data = await ToolResultStore().execute_sql(
                sql=str(args.get("sql") or ""), run_id=run_id,
                tenant_id=ctx.tenant_id, user_id=ctx.user_id,
                call_id=call_id,
                task_id=str(ctx.extra.get("runtime_task_id") or "") or None,
                agent_execution_id=str(ctx.extra.get("run_id") or "") or None,
            )
            stored_result = data.pop("_stored_result")
            log.info("sql_result_saved", result_id=stored_result["result_id"], row_count=data["row_count"])
            return ToolResult.ok(data, logs=log.entries_dict(), stored_result=stored_result)
        except ToolResultStoreError as exc:
            log.warning("sql_query_failed", reason=str(exc))
            return ToolResult.fail(str(exc), logs=log.entries_dict())
        except SQLAlchemyError as exc:
            logger.exception("result.analyze SQL execution failed run_id=%s", run_id)
            log.error("sql_query_failed", reason="database_error", error_type=type(exc).__name__)
            return ToolResult.fail(f"SQL query failed ({type(exc).__name__}).", logs=log.entries_dict())

    async def _analyze(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_notes(self.tool_slug)
        run_id = str(ctx.extra.get("runtime_root_run_id") or "").strip()
        result_id = str(args.get("result_id") if args.get("result_id") is not None else "").strip()
        if not run_id:
            return ToolResult.fail("Current runtime run_id is unavailable; cannot read a stored result.", logs=log.entries_dict())
        if not result_id:
            return ToolResult.fail("result_id is required; use the result_id from a successful tool result.", logs=log.entries_dict())
        try:
            data = await ToolResultStore().analyze(
                result_id=result_id,
                run_id=run_id,
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                mode=str(args.get("mode") or ""),
                array_path=str(args.get("array_path") or ""),
                fields=_path_list(args, "fields"),
                paths=_path_list(args, "paths"),
                text_path=str(args.get("text_path") or ""),
                text_offset=_integer_arg(args, "text_offset", 0),
                text_limit=_integer_arg(args, "text_limit", 1500),
                group_by=str(args.get("group_by") or ""),
                filter_path=str(args.get("filter_path") or ""),
                equals=args.get("equals"),
                equals_provided="equals" in args,
                offset=_integer_arg(args, "offset", 0),
                limit=_integer_arg(args, "limit", 25),
            )
            log.info("result_analyzed", mode=data.get("mode"), result_id=result_id)
            return ToolResult.ok(data, logs=log.entries_dict())
        except ToolResultStoreError as exc:
            log.warning("result_analysis_failed", reason=str(exc))
            return ToolResult.fail(str(exc), logs=log.entries_dict())
        except SQLAlchemyError as exc:
            cause = getattr(exc, "orig", exc)
            while getattr(cause, "__cause__", None) is not None:
                cause = cause.__cause__
            error_type = type(cause).__name__
            error_detail = str(cause).splitlines()[0][:240]
            logger.exception("result.analyze query failed run_id=%s result_id=%s mode=%s", run_id, result_id, args.get("mode"))
            log.error("result_analysis_failed", reason="query_error", error_type=error_type)
            return ToolResult.fail(
                f"result.analyze database query failed ({error_type}): {error_detail}",
                logs=log.entries_dict(),
            )
        except Exception as exc:
            logger.exception(
                "result.analyze internal failure run_id=%s result_id=%s mode=%s error_type=%s",
                run_id, result_id, args.get("mode"), type(exc).__name__,
            )
            log.error("result_analysis_failed", reason="internal_error", error_type=type(exc).__name__)
            return ToolResult.fail(
                f"result.analyze failed internally ({type(exc).__name__}); see API logs for the traceback.",
                logs=log.entries_dict(),
            )


def _integer_arg(args: Dict[str, Any], key: str, default: int) -> int:
    value = args.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        raise ToolResultStoreError(f"{key} must be an integer, not a boolean")
    if isinstance(value, float) and not value.is_integer():
        raise ToolResultStoreError(f"{key} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ToolResultStoreError(f"{key} must be an integer") from exc
    minimum = 1 if key in {"limit", "text_limit"} else 0
    if parsed < minimum:
        raise ToolResultStoreError(f"{key} must be >= {minimum}")
    return parsed


def _path_list(args: Dict[str, Any], key: str) -> list[str]:
    value = args.get(key)
    if value is None:
        return []
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ToolResultStoreError(f"{key} must be an array of JSON paths")
    return value
