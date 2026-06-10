"""
template.get_schema — Retrieve the fillable schema for a template row.

Given a collection and row_id, returns the template_schema JSON blob,
which describes the fillable structure (fields, placeholders, expected types).
"""
from __future__ import annotations

from typing import Any, ClassVar, Dict

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
        "row_id": {
            "type": "string",
            "description": "UUID of the template row",
        },
    },
    "required": ["collection_id", "row_id"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "row_id": {"type": "string"},
        "title": {"type": "string"},
        "source": {"type": "string"},
        "template_version": {"type": "string"},
        "template_schema": {"type": "object"},
        "description": {"type": "string"},
    },
}


@register_tool
class TemplateGetSchemaTool(VersionedTool):
    """Get the fillable schema for a template."""

    tool_slug: ClassVar[str] = "template.get_schema"
    domains: ClassVar[list] = ["system"]
    name: ClassVar[str] = "Get Template Schema"
    description: ClassVar[str] = (
        "Retrieve the fillable schema for a template row. "
        "Returns the template_schema JSON blob that describes fields, placeholders, and expected types."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Get template schema",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_logger("template.get_schema")

        collection_id = str(args.get("collection_id") or "").strip()
        row_id = str(args.get("row_id") or "").strip()
        if not collection_id or not row_id:
            log.error("Missing collection_id or row_id")
            return ToolResult.fail(
                "Missing 'collection_id' or 'row_id' argument",
                logs=log.entries_dict(),
            )

        try:
            import uuid
            session_factory = get_session_factory()
            async with session_factory() as session:
                service = CollectionService(session)
                try:
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

                rid = uuid.UUID(row_id)
                row_service = CollectionRowService(session)
                row = await row_service.get_row_by_id(collection, rid)
                if not row:
                    return ToolResult.fail(
                        f"Template row '{row_id}' not found in collection '{collection_id}'",
                        logs=log.entries_dict(),
                    )

                schema = row.get("template_schema") or {}
                if not schema:
                    return ToolResult.ok(
                        data={
                            "row_id": str(row["id"]),
                            "title": row.get("title") or "",
                            "source": row.get("source") or "",
                            "template_version": row.get("template_version") or "",
                            "template_schema": {},
                            "description": row.get("description") or "",
                        },
                        message="Template row exists but has no schema defined yet. Use template.fill with placeholder values.",
                        logs=log.entries_dict(),
                    )

                return ToolResult.ok(
                    data={
                        "row_id": str(row["id"]),
                        "title": row.get("title") or "",
                        "source": row.get("source") or "",
                        "template_version": row.get("template_version") or "",
                        "template_schema": schema,
                        "description": row.get("description") or "",
                    },
                    message=f"Schema for '{row.get('title') or row_id}' retrieved ({len(schema.get('fields', []))} field(s)).",
                    logs=log.entries_dict(),
                )
        except Exception as exc:
            logger.error("template.get_schema failed: %s", exc, exc_info=True)
            log.error("template.get_schema failed", error=str(exc))
            return ToolResult.fail(f"Failed to get schema: {exc}", logs=log.entries_dict())
