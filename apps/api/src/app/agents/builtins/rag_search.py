"""
RAG Search Tool - поиск по базе знаний (VersionedTool)
"""
from __future__ import annotations
from typing import Any, Dict, List, ClassVar
from app.core.logging import get_logger

from app.agents.handlers.versioned_tool import VersionedTool, tool_version, register_tool
from app.agents.context import ToolContext, ToolResult
from app.services.rag_search_service import RagSearchService, SearchResult

logger = get_logger(__name__)

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The search query to find relevant documents"
        },
        "k": {
            "type": "integer",
            "description": "Number of results to return (default: 5, max: 20)",
            "default": 5,
            "minimum": 1,
            "maximum": 20
        },
        "scope": {
            "type": "string",
            "description": "Search scope: 'tenant' (only tenant docs), 'global' (shared docs), 'all' (both)",
            "enum": ["tenant", "global", "all"],
            "default": "tenant"
        }
    },
    "required": ["query"]
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "hits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "source_id": {"type": "string"},
                    "page": {"type": "integer"},
                    "score": {"type": "number"}
                }
            }
        },
        "total": {"type": "integer"}
    }
}


@register_tool
class RagSearchTool(VersionedTool):
    """
    Tool для поиска по векторной базе знаний (RAG).
    
    Поддерживает:
    - Поиск по tenant-specific коллекциям
    - Scope фильтрацию (tenant/global/all)
    - Настраиваемое количество результатов
    """
    
    tool_slug: ClassVar[str] = "rag.search"
    tool_group: ClassVar[str] = "rag"
    name: ClassVar[str] = "Knowledge Base Search"
    description: ClassVar[str] = (
        "Search the company knowledge base for relevant information. "
        "Use this tool when you need to find documentation, policies, "
        "technical guides, or any other stored knowledge."
    )
    
    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Initial version with semantic search, scope filtering, configurable k",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        """
        Выполнить поиск по RAG.
        """
        log = ctx.tool_logger("rag.search")
        
        query = args["query"]
        k = min(args.get("k", 5), 20)
        scope = args.get("scope", "tenant")
        
        log.info("Starting RAG search", query=query[:100], k=k, scope=scope,
                 tenant_id=str(ctx.tenant_id))
        
        try:
            service = RagSearchService()
            
            log.debug("Calling search service")
            results = await service.search(
                tenant_id=ctx.tenant_id,
                query=query,
                k=k
            )
            
            if not results:
                log.info("No results found")
                return ToolResult.ok(
                    data={"hits": [], "total": 0},
                    message="No relevant documents found",
                    logs=log.entries_dict(),
                )
            
            hits = []
            sources = []
            
            for result in results:
                hit = self._format_hit(result)
                hits.append(hit)
                
                sources.append({
                    "source_id": result.source_id,
                    "source_name": result.source_name,
                    "chunk_id": result.chunk_id,
                    "text": result.text[:200],
                    "page": result.page,
                    "score": result.score,
                    "meta": result.meta
                })
            
            log.info("Search completed", hits_count=len(hits),
                     top_score=round(results[0].score, 3) if results else 0)
            
            return ToolResult.ok(
                data={
                    "hits": hits,
                    "total": len(hits)
                },
                sources=sources,
                logs=log.entries_dict(),
            )
            
        except Exception as e:
            logger.error(f"RAG search failed: {e}", exc_info=True)
            log.error("Search failed", error=str(e))
            return ToolResult.fail(f"Search failed: {str(e)}",
                                   logs=log.entries_dict())
    
    def _format_hit(self, result: SearchResult) -> Dict[str, Any]:
        """Форматировать результат для LLM"""
        text = result.text.strip()
        if len(text) > 500:
            text = text[:497] + "..."
        
        hit = {
            "text": text,
            "source_id": result.source_id,
            "page": result.page,
            "score": round(result.score, 3)
        }
        
        if result.model_hits:
            hit["models"] = ", ".join([
                f"{h['alias']}({h['score']:.2f})" 
                for h in result.model_hits
            ])
        
        return hit
