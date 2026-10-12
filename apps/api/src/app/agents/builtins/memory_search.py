"""Read-only bounded semantic-memory operation."""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.db import get_session_factory
from app.services.hipporag_service import HippoRAGService
from app.runtime.memory.search_contract import HippoMemorySearchInput


@register_tool
class MemorySearchTool(VersionedTool):
    tool_slug: ClassVar[str] = "memory.search"
    domains: ClassVar[list] = ["system", "memory"]
    name: ClassVar[str] = "Search Memory"
    description: ClassVar[str] = "Search the shared HippoRAG document memory graph. Supply a query and optional limit."


    @tool_version(
        version="1.0.0",
        input_schema=HippoMemorySearchInput.model_json_schema(),
        output_schema={"type": "object", "properties": {"items": {"type": "array"}, "backend": {"type": "string"}, "document_count": {"type": "integer"}, "index": {"type": ["string", "null"]}, "memory_context": {"type": "object"}, "count": {"type": "integer"}}},
        description="Search the shared persistent HippoRAG document corpus",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        request = HippoMemorySearchInput.model_validate(args)
        async with get_session_factory()() as session:
            result = await HippoRAGService(session).search_documents(request.query, limit=request.limit)
        items = []
        references = []
        for hit in result.get("hits", []):
            metadata = dict(hit.get("metadata") or {})
            sources = metadata.get("source_refs") or [metadata]
            refs = [{"document_id": source.get("document_id"),
                     "document_title": source.get("document_title"),
                     "filename": source.get("filename")} for source in sources]
            references.extend(refs)
            items.append({"kind": "document_passage", "subject": metadata.get("document_title") or "",
                          "text": hit["text"], "score": hit["score"], "metadata": metadata,
                          "source_references": refs})
        return ToolResult.ok({"backend": "hipporag", "index": result.get("index"),
            "document_count": result.get("document_count", 0), "items": items, "count": len(items),
            "memory_context": {"type": "memory_recall", "relevant_knowledge": items,
                               "source_references": references, "rag_required": not bool(items)}},
            delivery="direct")
