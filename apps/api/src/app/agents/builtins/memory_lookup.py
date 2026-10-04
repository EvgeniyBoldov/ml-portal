"""Read-only name and alias lookup for published memory scopes."""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.db import get_session_factory
from app.runtime.memory.mechanical_lookup import MechanicalLookupService


@register_tool
class MemoryLookupTool(VersionedTool):
    tool_slug: ClassVar[str] = "memory.lookup"
    domains: ClassVar[list] = ["system", "memory"]
    name: ClassVar[str] = "Lookup Memory Scopes"
    description: ClassVar[str] = "Find active scope and confirmed glossary identities by name or alias. Returns no memory facts."

    @tool_version(
        version="1.0.0",
        input_schema={"type": "object", "properties": {"query": {"type": "string", "minLength": 1}},
                      "required": ["query"], "additionalProperties": False},
        output_schema={"type": "object", "properties": {
            "scope_candidates": {"type": "array"}, "scope_ambiguities": {"type": "array"},
            "glossary": {"type": "array"}, "scope_candidates_truncated": {"type": "boolean"}},
            "required": ["scope_candidates"]},
        description="Lookup active scope and glossary identities without retrieving memory values",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult.fail("query is required")
        async with get_session_factory()() as session:
            result = await MechanicalLookupService(session).lookup(
                query=query, tenant_id=ctx.tenant_id,
            )
        return ToolResult.ok(result)
