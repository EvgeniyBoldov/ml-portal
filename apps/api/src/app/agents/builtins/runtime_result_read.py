"""Read a previously observed runtime tool result by its opaque reference."""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version


@register_tool
class RuntimeResultReadTool(VersionedTool):
    tool_slug: ClassVar[str] = "runtime.result.read"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Read Runtime Result"
    description: ClassVar[str] = "Read a bounded runtime-owned tool result by result_ref."

    @tool_version(
        version="1.0.0",
        input_schema={
            "type": "object",
            "properties": {"result_ref": {"type": "string", "minLength": 1}},
            "required": ["result_ref"],
            "additionalProperties": False,
        },
        output_schema={"type": "object"},
        description="Read one runtime result within the current task boundary",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        ref = str(args.get("result_ref") or "").strip()
        store = ctx.extra.get("runtime_result_store")
        plan_id = ctx.extra.get("runtime_plan_id")
        task_id = ctx.extra.get("runtime_task_id")
        if not ref or store is None or not plan_id or not task_id:
            return ToolResult.fail("Runtime result context is unavailable")
        try:
            value = await store.read(plan_id=plan_id, task_id=str(task_id), result_ref=ref)
        except KeyError as exc:
            return ToolResult.fail(str(exc))
        return ToolResult.ok(data=value)
