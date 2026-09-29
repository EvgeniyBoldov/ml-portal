"""Bounded analysis of a complete tool result from the current runtime run."""
from __future__ import annotations

from typing import Any, ClassVar, Dict
from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.services.tool_result_store import ToolResultStore, ToolResultStoreError

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "result_id": {"type": "string", "minLength": 1},
        "mode": {"type": "string", "enum": ["overview", "select", "aggregate"]},
        "array_path": {"type": "string"},
        "fields": {"type": "array", "items": {"type": "string"}, "maxItems": 20},
        "group_by": {"type": "string"},
        "filter_path": {"type": "string"},
        "equals": {"type": "string"},
        "offset": {"type": "integer", "minimum": 0},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    },
    "required": ["result_id", "mode"],
    "additionalProperties": False,
}

_OUTPUT_SCHEMA = {
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


@register_tool
class ResultAnalyzeTool(VersionedTool):
    tool_slug: ClassVar[str] = "result.analyze"
    domains: ClassVar[list] = ["system", "runtime"]
    name: ClassVar[str] = "Analyze Tool Result"
    description: ClassVar[str] = (
        "Inspect or query the complete stored result of a successful tool call in the current run. "
        "Use overview for field and array counts, select for bounded rows with pagination, "
        "and aggregate for exact counts or grouped counts. Never infer completeness from a preview."
    )

    @tool_version(version="1.0.0", input_schema=_INPUT_SCHEMA, output_schema=_OUTPUT_SCHEMA,
                  description="Run-scoped PostgreSQL JSONB result overview and bounded analytics")
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_logger(self.tool_slug)
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
        except Exception:
            log.error("result_analysis_failed", reason="store_error")
            return ToolResult.fail("Could not analyze the stored result.", logs=log.entries_dict())
