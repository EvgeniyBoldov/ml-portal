"""
template.list — List templates in a template collection.

Returns metadata for each template row: title, version, source, description,
and identifiers needed for get_schema/fill.
"""
from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.models.collection import CollectionType
from app.services.collection.row_service import CollectionRowService
from app.services.collection_service import CollectionService

logger = get_logger(__name__)

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection_id": {
            "type": "string",
            "description": "UUID or slug of the template collection",
        },
        "query": {
            "type": "string",
            "description": "Optional free-text filter (matches configured searchable fields)",
        },
        "limit": {
            "type": "integer",
            "description": "Max results to return",
            "default": 20,
        },
    },
    "required": ["collection_id"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "templates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "row_id": {"type": "string"},
                    "title": {"type": "string"},
                    "source": {"type": "string"},
                    "template_version": {"type": "string"},
                    "description": {"type": "string"},
                    "file_id": {"type": "string"},
                },
            },
        },
        "total": {"type": "integer"},
    },
}


@register_tool
class TemplateListTool(VersionedTool):
    """List templates in a template collection."""

    tool_slug: ClassVar[str] = "template.list"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "List Templates"
    description: ClassVar[str] = (
        "List templates in a template collection. Returns metadata for each template: "
        "title, version, source, description, and row_id needed for get_schema/fill."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="List templates in a collection",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_logger("template.list")

        collection_id = str(args.get("collection_id") or "").strip()
        if not collection_id:
            log.error("Missing collection_id")
            return ToolResult.fail("Missing 'collection_id' argument", logs=log.entries_dict())

        query_filter = str(args.get("query") or "").strip() or None
        limit = int(args.get("limit", 20))

        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                service = CollectionService(session)
                # Try UUID first, then slug
                try:
                    import uuid
                    cid = uuid.UUID(collection_id)
                    collection = await service.get_by_id(cid)
                except ValueError:
                    collection = await service.get_by_slug(collection_id)

                if not collection:
                    return ToolResult.fail(
                        f"Collection '{collection_id}' not found",
                        logs=log.entries_dict(),
                    )

                if collection.collection_type != CollectionType.TEMPLATE.value:
                    return ToolResult.fail(
                        f"Collection '{collection_id}' is not a template collection",
                        logs=log.entries_dict(),
                    )

                row_service = CollectionRowService(session)
                rows = await row_service.search(
                    collection,
                    limit=limit,
                    offset=0,
                    query=query_filter,
                )
                total = await row_service.count(collection, query=query_filter)

                templates = []
                for row in rows:
                    file_meta = row.get("file") or {}
                    templates.append({
                        "row_id": str(row.get("id")),
                        "title": row.get("title") or "",
                        "source": row.get("source") or "",
                        "template_version": row.get("template_version") or "",
                        "description": row.get("description") or "",
                        "file_id": file_meta.get("file_id") or "",
                    })

                return ToolResult.ok(
                    data={"templates": templates, "total": total},
                    message=f"Found {len(templates)} template(s) in collection '{collection.name}'.",
                    logs=log.entries_dict(),
                )
        except Exception as exc:
            logger.error("template.list failed: %s", exc, exc_info=True)
            log.error("template.list failed", error=str(exc))
            return ToolResult.fail(f"Failed to list templates: {exc}", logs=log.entries_dict())
