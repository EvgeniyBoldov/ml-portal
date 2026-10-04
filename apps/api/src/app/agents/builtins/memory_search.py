"""Read-only bounded semantic-memory operation."""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.db import get_session_factory
from app.runtime.memory.search import MemorySearchService
from app.runtime.memory.execution_context import memory_execution_context
from app.runtime.memory.search_contract import MemorySearchInput


@register_tool
class MemorySearchTool(VersionedTool):
    tool_slug: ClassVar[str] = "memory.search"
    domains: ClassVar[list] = ["system", "memory"]
    name: ClassVar[str] = "Search Memory"
    description: ClassVar[str] = (
        "Search allowed project/company long memory and confirmed glossary terms with "
        "bounded, source-aware results. Use it to resolve an abbreviation or retrieve "
        "project knowledge or confirmed owned facts (scopes=user/tenant, optional fact_subject). "
        "Use the application-provided execution_context fact. Always retain all its teams; "
        "choose known projects, [] for outside projects, or project.all for common rules only. "
        "It is not a source of current external-system state."
    )

    @tool_version(
        version="1.0.0",
        input_schema=MemorySearchInput.model_json_schema(),
        output_schema={"type": "object", "properties": {"items": {"type": "array"}, "projects": {"type": "array"}, "glossary": {"type": "array"}, "facts": {"type": "array"}, "groups": {"type": "array"}, "search_scope": {"type": "object"}, "execution_context": {"type": "object"}, "memory_context": {"type": "object"}, "count": {"type": "integer"}}},
        description="Bounded ACL-aware long-memory and glossary search",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        args = MemorySearchInput.model_validate(args).model_dump(exclude_unset=True)
        query = str(args.get("query") or "").strip()
        if not query:
            return ToolResult.fail("query is required")
        execution = ctx.extra.get("memory_execution_context")
        context_keys = ([*execution.get("team_keys", []), *execution.get("focused_project_keys", [])]
                        if isinstance(execution, dict) else
                        list((ctx.extra.get("project_context") or {}).get("effective_scope_keys") or []))
        async with get_session_factory()() as session:
            data = await MemorySearchService(session).search(
                query=query, tenant_id=ctx.tenant_id, user_id=ctx.user_id,
                team_keys=args.get("team_keys"), project_keys=args.get("project_keys"),
                context_scope_keys=context_keys, enforce_context=True,
                scopes=[str(value) for value in args.get("scopes") or []],
                kinds=[str(value) for value in args.get("kinds") or []],
                entity_ids=[str(value) for value in args.get("entity_ids") or []],
                direction=str(args.get("direction") or "").strip() or None,
                limit=int(args.get("limit") or 8), fact_subject=args.get("fact_subject"),
            )
        if data.get("success") is False:
            return ToolResult.fail(data["error_code"], uncertainties=data["uncertainties"])
        data["execution_context"] = execution if isinstance(execution, dict) else memory_execution_context(context_keys)
        return ToolResult.ok(data)
