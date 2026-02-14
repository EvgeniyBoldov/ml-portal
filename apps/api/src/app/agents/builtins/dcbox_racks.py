"""
DCBox — Racks tool (NetBox /api/dcim/racks/)
"""
from __future__ import annotations
from typing import Any, Dict, ClassVar

from app.core.logging import get_logger
from app.agents.handlers.versioned_tool import tool_version, register_tool
from app.agents.context import ToolContext, ToolResult
from app.agents.builtins.dcbox_base import RemoteApiTool, DEFAULT_LIMIT

logger = get_logger(__name__)

ENDPOINT = "/api/dcim/racks/"

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Filter by rack name (contains, case-insensitive)",
        },
        "site": {
            "type": "string",
            "description": "Filter by site name or slug",
        },
        "status": {
            "type": "string",
            "description": "Filter by status: active, planned, reserved, deprecated",
            "enum": ["active", "planned", "reserved", "deprecated"],
        },
        "role": {
            "type": "string",
            "description": "Filter by rack role slug",
        },
        "tenant": {
            "type": "string",
            "description": "Filter by tenant slug",
        },
        "id": {
            "type": "integer",
            "description": "Get a single rack by its ID",
        },
        "q": {
            "type": "string",
            "description": "General search query",
        },
        "limit": {
            "type": "integer",
            "description": "Max results (default 50, max 200)",
            "default": 50,
        },
        "offset": {
            "type": "integer",
            "description": "Pagination offset",
            "default": 0,
        },
    },
    "required": [],
}

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "status": {"type": "object"},
                    "site": {"type": "object"},
                    "role": {"type": "object"},
                    "tenant": {"type": "object"},
                    "u_height": {"type": "integer"},
                    "device_count": {"type": "integer"},
                },
            },
        },
        "count": {"type": "integer"},
        "returned": {"type": "integer"},
        "has_more": {"type": "boolean"},
    },
}


@register_tool
class DCBoxRacksTool(RemoteApiTool):
    """Search and list racks from DCBox (NetBox) DCIM module."""

    tool_slug: ClassVar[str] = "dcbox.racks"
    tool_group: ClassVar[str] = "dcbox"
    name: ClassVar[str] = "DCBox Racks"
    description: ClassVar[str] = (
        "Search and list server racks from DCBox/NetBox. "
        "Can filter by name, site, status, role, tenant. "
        "Returns rack details including height, device count, and location."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        description="List and search racks with filters",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        rack_id = args.get("id")
        if rack_id:
            return await self._fetch_detail(ctx, ENDPOINT, rack_id)

        params = {}
        if args.get("name"):
            params["name__ic"] = args["name"]
        if args.get("site"):
            params["site"] = args["site"]
        if args.get("status"):
            params["status"] = args["status"]
        if args.get("role"):
            params["role"] = args["role"]
        if args.get("tenant"):
            params["tenant"] = args["tenant"]
        if args.get("q"):
            params["q"] = args["q"]

        return await self._fetch_list(
            ctx,
            ENDPOINT,
            params=params,
            limit=args.get("limit", DEFAULT_LIMIT),
            offset=args.get("offset", 0),
        )
