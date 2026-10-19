"""Read-only bounded semantic-memory operation."""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.db import get_session_factory
from app.services.hipporag_service import HippoRAGService
from app.runtime.memory.search_contract import HippoMemorySearchInput, HippoMemorySearchResult


@register_tool
class MemorySearchTool(VersionedTool):
    tool_slug: ClassVar[str] = "memory.search"
    domains: ClassVar[list] = ["system", "memory"]
    name: ClassVar[str] = "Search Memory"
    description: ClassVar[str] = "Search each selected chat scope independently in parallel. Supply query and optional limit per scope; scope selection is application-owned."


    @tool_version(
        version="1.0.0",
        input_schema=HippoMemorySearchInput.model_json_schema(),
        output_schema=HippoMemorySearchResult.model_json_schema(),
        description="Search the independent HippoRAG corpora selected in this chat",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        request = HippoMemorySearchInput.model_validate(args)
        execution = ctx.extra.get("memory_execution_context") or {}
        project_context = ctx.extra.get("project_context") or {}
        scope_context = project_context.get("scope_context") or {}
        scope_keys = list(ctx.extra.get("memory_search_scope_keys", scope_context.get("keys", execution.get("scope_keys", []))))
        async with get_session_factory()() as session:
            result = await HippoRAGService(session).search_documents(
                request.query, scope_keys=scope_keys, limit=request.limit,
            )
        groups = []
        for group in result.get("groups", []):
            items = []
            references = []
            for hit in group.get("hits", []):
                metadata = dict(hit.get("metadata") or {})
                sources = metadata.get("source_refs") or [metadata]
                refs = [{"document_id": source.get("document_id"),
                         "document_title": source.get("document_title"),
                         "filename": source.get("filename")} for source in sources]
                references.extend(ref for ref in refs if ref not in references)
                items.append({"kind": "document_passage", "scope_slug": group["scope_slug"],
                              "subject": metadata.get("document_title") or "",
                              "text": hit["text"], "score": hit["score"], "metadata": metadata,
                              "source_references": refs})
            groups.append({key: value for key, value in {
                "scope_slug": group["scope_slug"], "status": group["status"],
                "success": group["success"], "index": group.get("index"),
                "document_count": group.get("document_count", 0),
                "items": items, "count": len(items), "source_references": references,
                "error_code": group.get("error_code"), "error": group.get("error"),
            }.items() if value is not None})
        return ToolResult.ok({"backend": "hipporag", "groups": groups, "group_count": len(groups),
                              "partial": any(not group["success"] for group in groups)}, delivery="direct")
