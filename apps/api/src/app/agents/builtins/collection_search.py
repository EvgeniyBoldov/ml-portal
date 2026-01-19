"""
Collection Search Tool - универсальный поиск по SQL-коллекциям
"""
from __future__ import annotations
from typing import Any, Dict, List, ClassVar, Optional
import uuid

from app.core.logging import get_logger
from app.agents.handlers.base import ToolHandler
from app.agents.context import ToolContext, ToolResult
from app.models.collection import Collection, SearchMode

logger = get_logger(__name__)


class CollectionSearchTool(ToolHandler):
    """
    Динамический Tool для поиска по SQL-коллекциям.
    
    Этот tool создаётся динамически для каждой коллекции,
    input_schema генерируется из схемы полей коллекции.
    """
    
    slug: ClassVar[str] = "collection.search"
    name: ClassVar[str] = "Collection Search"
    description: ClassVar[str] = "Search in a data collection"
    
    input_schema: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {
            "collection_slug": {
                "type": "string",
                "description": "The collection to search in"
            },
            "query": {
                "type": "string",
                "description": "Search query (searches in text fields with LIKE)"
            },
            "filters": {
                "type": "object",
                "description": "Field-specific filters",
                "additionalProperties": True
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default: 50)",
                "default": 50,
                "minimum": 1,
                "maximum": 100
            }
        },
        "required": ["collection_slug"]
    }
    
    output_schema: ClassVar[Dict[str, Any]] = {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {"type": "object"}
            },
            "total": {"type": "integer"},
            "collection": {"type": "string"}
        }
    }

    @classmethod
    def build_schema_for_collection(cls, collection: Collection) -> Dict[str, Any]:
        """
        Генерирует input_schema для конкретной коллекции.
        Используется для формирования инструкций LLM.
        """
        properties = {
            "query": {
                "type": "string",
                "description": f"Free text search across text fields in '{collection.name}'"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 50)",
                "default": 50
            }
        }
        
        for field in collection.get_searchable_fields():
            field_name = field["name"]
            field_type = field["type"]
            search_mode = field.get("search_mode", SearchMode.EXACT.value)
            field_desc = field.get("description", f"Filter by {field_name}")
            
            if search_mode == SearchMode.RANGE.value:
                properties[f"{field_name}_from"] = {
                    "type": cls._map_field_type(field_type),
                    "description": f"{field_desc} (from/minimum)"
                }
                properties[f"{field_name}_to"] = {
                    "type": cls._map_field_type(field_type),
                    "description": f"{field_desc} (to/maximum)"
                }
            else:
                properties[field_name] = {
                    "type": cls._map_field_type(field_type),
                    "description": field_desc
                }
        
        return {
            "type": "object",
            "properties": properties,
            "required": []
        }

    @classmethod
    def _map_field_type(cls, field_type: str) -> str:
        """Map collection field type to JSON Schema type"""
        mapping = {
            "text": "string",
            "integer": "integer",
            "float": "number",
            "boolean": "boolean",
            "datetime": "string",
            "date": "string",
        }
        return mapping.get(field_type, "string")

    async def execute(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        """
        Выполнить поиск по коллекции.
        """
        from app.core.db import get_session_factory
        from app.services.collection_service import CollectionService
        
        collection_slug = args.get("collection_slug")
        query = args.get("query")
        filters = args.get("filters", {})
        limit = min(args.get("limit", 50), 100)
        
        logger.info(
            f"Collection search: collection={collection_slug}, "
            f"query='{query[:50] if query else ''}', filters={filters}, "
            f"tenant={ctx.tenant_id}"
        )
        
        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                service = CollectionService(session)
                
                collection = await service.get_by_slug(ctx.tenant_id, collection_slug)
                if not collection:
                    return ToolResult.fail(
                        f"Collection '{collection_slug}' not found"
                    )
                
                search_filters = self._build_filters(collection, args)
                
                rows = await service.search(
                    collection=collection,
                    filters=search_filters,
                    limit=limit,
                    query=query,
                )
                
                total = await service.count(collection, search_filters, query=query)
                
                formatted_rows = self._format_rows(rows, collection)
                
                logger.info(f"Collection search found {len(formatted_rows)} results")
                
                return ToolResult.ok(
                    data={
                        "rows": formatted_rows,
                        "total": total,
                        "collection": collection.name,
                        "returned": len(formatted_rows),
                    }
                )
                
        except Exception as e:
            logger.error(f"Collection search failed: {e}", exc_info=True)
            return ToolResult.fail(f"Search failed: {str(e)}")

    def _build_filters(
        self,
        collection: Collection,
        args: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build filters dict from args (specific field filters only)"""
        filters = {}
        
        for field in collection.get_searchable_fields():
            field_name = field["name"]
            search_mode = field.get("search_mode", SearchMode.EXACT.value)
            
            if search_mode == SearchMode.RANGE.value:
                range_filter = {}
                if f"{field_name}_from" in args:
                    range_filter["from"] = args[f"{field_name}_from"]
                if f"{field_name}_to" in args:
                    range_filter["to"] = args[f"{field_name}_to"]
                if range_filter:
                    filters[field_name] = range_filter
            elif field_name in args:
                filters[field_name] = args[field_name]
        
        if "filters" in args and isinstance(args["filters"], dict):
            filters.update(args["filters"])
        
        return filters

    def _format_rows(
        self,
        rows: List[Dict],
        collection: Collection
    ) -> List[Dict[str, Any]]:
        """Format rows for LLM consumption"""
        formatted = []
        
        for row in rows:
            formatted_row = {}
            for field in collection.fields:
                field_name = field["name"]
                if field_name in row:
                    value = row[field_name]
                    if isinstance(value, (uuid.UUID,)):
                        value = str(value)
                    if field["type"] == "text" and value and len(str(value)) > 500:
                        value = str(value)[:497] + "..."
                    formatted_row[field_name] = value
            formatted.append(formatted_row)
        
        return formatted


def create_collection_tool(collection: Collection) -> Dict[str, Any]:
    """
    Создаёт описание tool для конкретной коллекции.
    Используется для генерации инструкций агенту.
    """
    schema = CollectionSearchTool.build_schema_for_collection(collection)
    
    return {
        "slug": f"collection.{collection.slug}.search",
        "name": f"Search {collection.name}",
        "description": collection.description or f"Search in {collection.name} collection",
        "input_schema": schema,
    }
