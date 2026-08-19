"""
collection.template.get_schema — retrieve the fill-ready schema for a template row.

Given a collection and row_id, returns the schema that the values payload must
match when filling the selected template.
"""
from __future__ import annotations

from typing import Any, ClassVar, Dict

from app.agents.context import ToolContext, ToolResult
from app.agents.handlers.versioned_tool import VersionedTool, register_tool, tool_version
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.models.collection import CollectionType
from app.services.collection.row_service import CollectionRowService
from app.services.collection.template_contract import TemplateContract
from app.services.collection_service import CollectionService

logger = get_logger(__name__)

_INPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "collection_slug": {
            "type": "string",
            "description": "Slug of the template collection",
        },
        "row_id": {
            "type": "string",
            "description": "UUID of the template row",
        },
    },
    "required": ["collection_slug", "row_id"],
}

_OUTPUT_SCHEMA_V1 = {
    "type": "object",
    "properties": {
        "row_id": {"type": "string"},
        "title": {"type": "string"},
        "source": {"type": "string"},
        "template_version": {"type": "string"},
        "template_schema": {"type": "object"},
        "runtime_schema": {"type": "object"},
        "description": {"type": "string"},
        "contract_version": {"type": "string"},
        "field_count": {"type": "integer"},
    },
}


@register_tool
class TemplateGetSchemaTool(VersionedTool):
    """Get the fill-ready schema contract for a template row."""

    tool_slug: ClassVar[str] = "collection.template.get_schema"
    domains: ClassVar[list] = ["collection.template"]
    name: ClassVar[str] = "Get Template Schema"
    description: ClassVar[str] = (
        "Retrieve the fill-ready schema for a template row. "
        "Returns the exact values contract that the fill input must match, including field names, nesting, and expected types."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA_V1,
        output_schema=_OUTPUT_SCHEMA_V1,
        description="Get template schema",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        log = ctx.tool_notes("collection.template.get_schema")

        collection_slug = str(args.get("collection_slug") or "").strip()
        # Existing persisted task payloads may still contain collection_id.
        # It is a compatibility input only; all published contracts use slug.
        legacy_collection_id = str(args.get("collection_id") or "").strip()
        row_id = str(args.get("row_id") or "").strip()
        if not (collection_slug or legacy_collection_id) or not row_id:
            log.error("Missing collection_slug or row_id")
            return ToolResult.fail(
                "Missing 'collection_slug' or 'row_id' argument",
                logs=log.entries_dict(),
            )

        try:
            import uuid
            session_factory = get_session_factory()
            async with session_factory() as session:
                service = CollectionService(session)
                if collection_slug:
                    collection = await service.get_by_slug(collection_slug)
                else:
                    try:
                        collection = await service.get_by_id(uuid.UUID(legacy_collection_id))
                    except ValueError:
                        collection = None

                if not collection:
                    return ToolResult.fail(
                        f"Collection '{collection_slug or legacy_collection_id}' not found",
                        logs=log.entries_dict(),
                    )
                if collection.collection_type != CollectionType.TEMPLATE.value:
                    return ToolResult.fail(
                        f"Collection '{collection_slug or legacy_collection_id}' is not a template collection",
                        logs=log.entries_dict(),
                    )

                rid = uuid.UUID(row_id)
                row_service = CollectionRowService(session)
                row = await row_service.get_row_by_id(collection, rid)
                if not row:
                    return ToolResult.fail(
                        f"Template row '{row_id}' not found in collection '{collection_slug or legacy_collection_id}'",
                        logs=log.entries_dict(),
                    )

                raw_schema = row.get("template_schema") or {}
                contract = TemplateContract.from_jsonb(raw_schema)
                
                if not contract.fields:
                    return ToolResult.fail(
                        "Template schema is not available for this row yet.",
                        logs=log.entries_dict(),
                    )

                # Return the fill-ready schema derived from the stored contract.
                return ToolResult.ok(
                    data={
                        "row_id": str(row["id"]),
                        "title": row.get("title") or "",
                        "source": row.get("source") or "",
                        "template_version": row.get("template_version") or "",
                        "template_schema": contract.to_fill_input_schema(),
                        "runtime_schema": contract.to_runtime_schema(),
                        "description": row.get("description") or "",
                        "contract_version": contract.contract_version,
                        "field_count": len(contract.fields),
                    },
                    message=f"Schema for '{row.get('title') or row_id}' retrieved ({len(contract.fields)} field(s)).",
                    logs=log.entries_dict(),
                )
        except Exception as exc:
            logger.error("collection.template.get_schema failed: %s", exc, exc_info=True)
            log.error("collection.template.get_schema failed", error=str(exc))
            return ToolResult.fail(f"Failed to get schema: {exc}", logs=log.entries_dict())
