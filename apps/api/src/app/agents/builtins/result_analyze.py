"""Bounded analysis of a complete tool result from the current runtime run."""
from __future__ import annotations

from typing import Any, ClassVar, Dict
from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.services.tool_result_store import ToolResultStore, ToolResultStoreError

_INPUT_SCHEMA_V1 = {
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
        "mode": {"type": "string", "enum": ["overview", "select", "aggregate", "project", "text"]},
        "paths": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1, "maxItems": 20},
        "text_path": {"type": "string", "minLength": 1},
        "text_offset": {"type": "integer", "minimum": 0},
        "text_limit": {"type": "integer", "minimum": 1, "maximum": 2000},
    },
}
_OUTPUT_SCHEMA_V1_1 = {
    **_OUTPUT_SCHEMA_V1,
    "properties": {
        **_OUTPUT_SCHEMA_V1["properties"],
        "values": {"type": "object"},
        "missing_paths": {"type": "array", "items": {"type": "string"}},
        "chunk": {"type": "string"},
        "length": {"type": "integer"},
        "text_path": {"type": "string"},
    },
}


@register_tool
class ResultAnalyzeTool(VersionedTool):
    tool_slug: ClassVar[str] = "result.analyze"
    domains: ClassVar[list] = ["system", "runtime"]
    name: ClassVar[str] = "Analyze Tool Result"
    description: ClassVar[str] = (
        "Inspect or query the complete stored result of a successful tool call in the current run. "
        "Use overview for field and array counts, project for selected object paths, "
        "text for long string fields, select for bounded array rows with pagination, and aggregate for exact counts or "
        "grouped counts. Never infer completeness from a preview."
    )

    @tool_version(version="1.0.0", input_schema=_INPUT_SCHEMA_V1, output_schema=_OUTPUT_SCHEMA_V1,
                  description="Run-scoped PostgreSQL JSONB result overview and bounded analytics")
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        return await self._analyze(ctx, args)

    @tool_version(version="1.1.0", input_schema=_INPUT_SCHEMA_V1_1, output_schema=_OUTPUT_SCHEMA_V1_1,
                  description="Adds bounded object projection and paginated text reads")
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
        except Exception:
            log.error("result_analysis_failed", reason="store_error")
            return ToolResult.fail("Could not analyze the stored result.", logs=log.entries_dict())
