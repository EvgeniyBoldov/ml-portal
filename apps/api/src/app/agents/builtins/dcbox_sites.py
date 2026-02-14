"""
DCBox — Sites tool (NetBox /api/dcim/sites/)
"""
from __future__ import annotations
from typing import Any, Dict, ClassVar

from app.core.logging import get_logger
from app.agents.handlers.versioned_tool import tool_version, register_tool
from app.agents.context import ToolContext, ToolResult
from app.agents.builtins.dcbox_base import RemoteApiTool, DEFAULT_LIMIT

logger = get_logger(__name__)

ENDPOINT = "/api/dcim/sites/"

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Filter by site name (contains, case-insensitive)",
        },
        "region": {
            "type": "string",
            "description": "Filter by region slug",
        },
        "status": {
            "type": "string",
            "description": "Filter by status: active, planned, staging, decommissioning, retired",
            "enum": ["active", "planned", "staging", "decommissioning", "retired"],
        },
        "tenant": {
            "type": "string",
            "description": "Filter by tenant slug",
        },
        "id": {
            "type": "integer",
            "description": "Get a single site by its ID",
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
                    "slug": {"type": "string"},
                    "status": {"type": "object"},
                    "region": {"type": "object"},
                    "tenant": {"type": "object"},
                    "facility": {"type": "string"},
                    "physical_address": {"type": "string"},
                    "description": {"type": "string"},
                },
            },
        },
        "count": {"type": "integer"},
        "returned": {"type": "integer"},
        "has_more": {"type": "boolean"},
    },
}


@register_tool
class DCBoxSitesTool(RemoteApiTool):
    """Search and list sites from DCBox (NetBox) DCIM module."""

    tool_slug: ClassVar[str] = "dcbox.sites"
    tool_group: ClassVar[str] = "dcbox"
    name: ClassVar[str] = "DCBox Sites"
    description: ClassVar[str] = (
        "Search and list data center sites from DCBox/NetBox. "
        "Can filter by name, region, status, tenant. "
        "Returns site details including address, facility, and region."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        description="List and search sites with filters",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        site_id = args.get("id")
        if site_id:
            return await self._fetch_detail(ctx, ENDPOINT, site_id)

        params = {}
        if args.get("name"):
            params["name__ic"] = args["name"]
        if args.get("region"):
            params["region"] = args["region"]
        if args.get("status"):
            params["status"] = args["status"]
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
