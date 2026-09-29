"""Bounded analysis of a complete tool result from the current runtime run."""
from __future__ import annotations

import logging
from typing import Any, ClassVar, Dict
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


@register_tool
class ResultAnalyzeTool(VersionedTool):
    tool_slug: ClassVar[str] = "result.analyze"
    domains: ClassVar[list] = ["system", "runtime"]
    name: ClassVar[str] = "Analyze Tool Result"
    description: ClassVar[str] = (
        "Inspect a successful tool result from this runtime run using its result_id. "
        "Modes and required arguments: overview(result_id); project(result_id, paths); "
        "text(result_id, text_path[, text_offset, text_limit]); "
        "select(result_id, array_path[, fields, offset, limit]); "
        "aggregate(result_id, array_path[, group_by, filter_path, equals]). "
        "Paths are dot-separated JSON paths. project is for object/scalar fields, not arrays. "
        "select is for arrays and must be paged until complete=true; text must be paged using next_offset "
        "until complete=true. A preview is never proof of completeness."
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

    async def _analyze(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_notes(self.tool_slug)
        run_id = str(ctx.extra.get("runtime_root_run_id") or "").strip()
        result_id = str(args.get("result_id") or "").strip()
        if not run_id or not result_id:
            return ToolResult.fail("A result from the current runtime run is required.", logs=log.entries_dict())
        try:
            data = await ToolResultStore().analyze(
                result_id=result_id,
                run_id=run_id,
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                mode=str(args.get("mode") or ""),
                array_path=str(args.get("array_path") or ""),
                fields=[str(item) for item in args.get("fields") or []],
                paths=[str(item) for item in args.get("paths") or []],
                text_path=str(args.get("text_path") or ""),
                text_offset=int(args.get("text_offset") or 0),
                text_limit=int(args.get("text_limit") or 1500),
                group_by=str(args.get("group_by") or ""),
                filter_path=str(args.get("filter_path") or ""),
                equals=str(args["equals"]) if args.get("equals") is not None else None,
                offset=int(args.get("offset") or 0),
                limit=int(args.get("limit") or 25),
            )
            log.info("result_analyzed", mode=data.get("mode"), result_id=result_id)
            return ToolResult.ok(data, logs=log.entries_dict())
        except ToolResultStoreError as exc:
            log.warning("result_analysis_failed", reason=str(exc))
            return ToolResult.fail(str(exc), logs=log.entries_dict())
        except Exception as exc:
            # Keep the user-facing result generic, but retain actionable diagnostics
            # in API container logs without logging payloads or tool arguments.
            logger.exception(
                "result.analyze internal failure run_id=%s result_id=%s mode=%s error_type=%s",
                run_id, result_id, args.get("mode"), type(exc).__name__,
            )
            log.error("result_analysis_failed", reason="internal_error", error_type=type(exc).__name__)
            return ToolResult.fail("Could not analyze the stored result.", logs=log.entries_dict())
