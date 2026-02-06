"""
Collection Get Tool - получение записи по ключу (VersionedTool)
"""
from __future__ import annotations
from typing import Any, Dict, ClassVar
import uuid

from app.core.logging import get_logger
from app.agents.handlers.versioned_tool import VersionedTool, tool_version, register_tool
from app.agents.context import ToolContext, ToolResult

logger = get_logger(__name__)

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection_slug": {
            "type": "string",
            "description": "The collection to get record from"
        },
        "id": {
            "type": "string",
            "description": "The primary key value (UUID or other key)"
        },
        "id_field": {
            "type": "string",
            "description": "Primary key field name (default: uses collection's primary_key_field)"
        }
    },
    "required": ["collection_slug", "id"]
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "record": {
            "type": "object",
            "description": "The found record or null"
        },
        "found": {
            "type": "boolean"
        },
        "collection": {
            "type": "string"
        }
    }
}


@register_tool
class CollectionGetTool(VersionedTool):
    """
    Tool для получения записи из коллекции по первичному ключу.
    
    Используется для точного получения одной записи по ID или другому ключу.
    """
    
    tool_slug: ClassVar[str] = "collection.get"
    tool_group: ClassVar[str] = "collection"
    name: ClassVar[str] = "Collection Get"
    description: ClassVar[str] = "Get a single record from a collection by its primary key"
    
    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Initial version with primary key lookup and custom id_field support",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        """
        Получить запись из коллекции по ключу.
        """
        from sqlalchemy import text
        from app.core.db import get_session_factory
        from app.services.collection_service import CollectionService
        
        collection_slug = args.get("collection_slug")
        record_id = args.get("id")
        id_field = args.get("id_field")
        
        logger.info(
            f"Collection get: collection={collection_slug}, "
            f"id={record_id}, tenant={ctx.tenant_id}"
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
                
                # Use collection's primary_key_field if not specified
                key_field = id_field or collection.primary_key_field
                
                # Validate key field exists
                field_def = collection.get_field_by_name(key_field)
                if not field_def and key_field != "id":
                    return ToolResult.fail(
                        f"Field '{key_field}' not found in collection"
                    )
                
                # Build and execute query
                table_name = collection.table_name
                sql = text(f"SELECT * FROM {table_name} WHERE {key_field} = :id LIMIT 1")
                
                result = await session.execute(sql, {"id": record_id})
                row = result.mappings().first()
                
                if not row:
                    return ToolResult.ok(
                        data={
                            "record": None,
                            "found": False,
                            "collection": collection.name,
                        }
                    )
                
                # Format record
                formatted = self._format_record(dict(row), collection)
                
                logger.info(f"Collection get found record in '{collection_slug}'")
                
                return ToolResult.ok(
                    data={
                        "record": formatted,
                        "found": True,
                        "collection": collection.name,
                    }
                )
                
        except Exception as e:
            logger.error(f"Collection get failed: {e}", exc_info=True)
            return ToolResult.fail(f"Get failed: {str(e)}")

    def _format_record(self, row: Dict, collection) -> Dict[str, Any]:
        """Format a single record for LLM consumption"""
        formatted = {}
        
        # Always include id
        if "id" in row:
            formatted["id"] = str(row["id"]) if isinstance(row["id"], uuid.UUID) else row["id"]
        
        for field in collection.fields:
            field_name = field["name"]
            if field_name in row:
                value = row[field_name]
                if isinstance(value, uuid.UUID):
                    value = str(value)
                # Truncate very long text fields
                if field["type"] == "text" and value and len(str(value)) > 1000:
                    value = str(value)[:997] + "..."
                formatted[field_name] = value
        
        return formatted
