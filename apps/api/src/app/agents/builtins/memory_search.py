"""Read-only bounded semantic-memory operation."""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.db import get_session_factory
from app.runtime.memory.search import MemorySearchService


@register_tool
class MemorySearchTool(VersionedTool):
    tool_slug: ClassVar[str] = "memory.search"
    domains: ClassVar[list] = ["system", "memory"]
    name: ClassVar[str] = "Search Memory"
    description: ClassVar[str] = (
        "Search allowed project/company long memory and confirmed glossary terms with "
        "bounded, source-aware results. Use it to resolve an abbreviation or retrieve "
        "project knowledge or confirmed owned facts (scopes=user/tenant, optional fact_subject). "
        "It is not a source of current external-system state."
    )

    @tool_version(
        version="1.0.0",
        input_schema={"type": "object", "properties": {
            "query": {"type": "string"}, "project_keys": {"type": "array", "items": {"type": "string"}},
            "scope_keys": {"type": "array", "items": {"type": "string"}},
            "scope_mode": {"type": "string", "enum": ["inherit", "replace"]},
            "kinds": {"type": "array", "items": {"type": "string"}},
            "entity_ids": {"type": "array", "items": {"type": "string"}},
            "direction": {"type": "string"},
            "fact_subject": {"type": "string", "maxLength": 200},
            "scopes": {"type": "array", "items": {"type": "string"}},
            "limit": {"type": "integer", "minimum": 1, "maximum": 12},
        }, "required": ["query"]},
        output_schema={"type": "object", "properties": {"items": {"type": "array"}, "projects": {"type": "array"}, "glossary": {"type": "array"}, "facts": {"type": "array"}, "count": {"type": "integer"}}},
        description="Bounded ACL-aware long-memory and glossary search",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult.fail("query is required")
        async with get_session_factory()() as session:
            data = await MemorySearchService(session).search(
                query=query, tenant_id=ctx.tenant_id, user_id=ctx.user_id,
                project_keys=[str(value) for value in args.get("project_keys") or []],
                fallback_project_keys=list((ctx.extra.get("project_context") or {}).get("effective_project_keys") or []),
                context_scope_keys=list((ctx.extra.get("project_context") or {}).get("effective_scope_keys") or []),
                scope_keys=[str(value) for value in args.get("scope_keys") or []],
                scope_mode=str(args.get("scope_mode") or "inherit"),
                scope_ceiling_keys=list((ctx.extra.get("project_context") or {}).get("scope_ceiling_keys",
                                        (ctx.extra.get("project_context") or {}).get("effective_scope_keys", [])) or []),
                scopes=[str(value) for value in args.get("scopes") or []],
                kinds=[str(value) for value in args.get("kinds") or []],
                entity_ids=[str(value) for value in args.get("entity_ids") or []],
                direction=str(args.get("direction") or "").strip() or None,
                limit=int(args.get("limit") or 8), fact_subject=args.get("fact_subject"),
            )
        if data.get("success") is False:
            return ToolResult.fail(data["error_code"], uncertainties=data["uncertainties"])
        return ToolResult.ok(data)
