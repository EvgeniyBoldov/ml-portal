"""System tools for reading and proposing project memory."""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.services.project_memory_service import ProjectMemoryService

_READ_INPUT = {
    "type": "object",
    "properties": {
        "project_key": {"type": "string", "minLength": 1},
        "subject_prefix": {"type": "string"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50},
    },
    "required": ["project_key"],
    "additionalProperties": False,
}
_READ_OUTPUT = {
    "type": "object",
    "properties": {"project": {"type": ["object", "null"]}, "facts": {"type": "array"}, "count": {"type": "integer"}},
    "required": ["project", "facts", "count"],
}
@register_tool
class ProjectMemoryReadTool(VersionedTool):
    tool_slug: ClassVar[str] = "project_memory.read"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Read Project Memory"
    description: ClassVar[str] = "Read confirmed compact knowledge for an exact project key."

    @tool_version(version="1.0.0", input_schema=_READ_INPUT, output_schema=_READ_OUTPUT, description="Read confirmed project memory")
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_notes(self.tool_slug)
        project_key = str(args.get("project_key") or "").strip().lower()
        if not project_key:
            return ToolResult.fail("Missing 'project_key' argument", logs=log.entries_dict())
        session_factory = ctx.get_runtime_deps().session_factory
        if session_factory is None:
            from app.core.db import get_session_factory
            session_factory = get_session_factory()
        async with session_factory() as session:
            data = await ProjectMemoryService(session).read(
                project_key=project_key,
                subject_prefix=str(args.get("subject_prefix") or "").strip() or None,
                limit=int(args.get("limit") or 20),
            )
        log.info("Project memory read", project_key=project_key, count=data["count"])
        return ToolResult.ok(data=data, logs=log.entries_dict())
