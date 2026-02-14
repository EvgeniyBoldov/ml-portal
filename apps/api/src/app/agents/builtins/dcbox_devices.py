"""
DCBox — Devices tool (NetBox /api/dcim/devices/)
"""
from __future__ import annotations
from typing import Any, Dict, ClassVar

from app.core.logging import get_logger
from app.agents.handlers.versioned_tool import tool_version, register_tool
from app.agents.context import ToolContext, ToolResult
from app.agents.builtins.dcbox_base import RemoteApiTool, DEFAULT_LIMIT

logger = get_logger(__name__)

ENDPOINT = "/api/dcim/devices/"

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Filter by device name (contains, case-insensitive)",
        },
        "site": {
            "type": "string",
            "description": "Filter by site name or slug",
        },
        "role": {
            "type": "string",
            "description": "Filter by device role slug (e.g. 'router', 'switch', 'server')",
        },
        "manufacturer": {
            "type": "string",
            "description": "Filter by manufacturer slug",
        },
        "status": {
            "type": "string",
            "description": "Filter by status: active, planned, staged, failed, offline, decommissioning",
            "enum": ["active", "planned", "staged", "failed", "offline", "decommissioning"],
        },
        "rack_id": {
            "type": "integer",
            "description": "Filter by rack ID",
        },
        "id": {
            "type": "integer",
            "description": "Get a single device by its ID",
        },
        "q": {
            "type": "string",
            "description": "General search query across all text fields",
        },
        "limit": {
            "type": "integer",
            "description": "Max results to return (default 50, max 200)",
            "default": 50,
        },
        "offset": {
            "type": "integer",
            "description": "Number of results to skip for pagination",
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
                    "rack": {"type": "object"},
                    "device_role": {"type": "object"},
                    "device_type": {"type": "object"},
                    "primary_ip": {"type": "object"},
                },
            },
        },
        "count": {"type": "integer"},
        "returned": {"type": "integer"},
        "has_more": {"type": "boolean"},
    },
}


@register_tool
class DCBoxDevicesTool(RemoteApiTool):
    """Search and list devices from DCBox (NetBox) DCIM module."""

    tool_slug: ClassVar[str] = "dcbox.devices"
    tool_group: ClassVar[str] = "dcbox"
    name: ClassVar[str] = "DCBox Devices"
    description: ClassVar[str] = (
        "Search and list network devices from DCBox/NetBox. "
        "Can filter by name, site, role, manufacturer, status, rack. "
        "Returns device details including IPs, rack position, and status."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        description="List and search devices with filters",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        device_id = args.get("id")
        if device_id:
            return await self._fetch_detail(ctx, ENDPOINT, device_id)

        params = {}
        if args.get("name"):
            params["name__ic"] = args["name"]
        if args.get("site"):
            params["site"] = args["site"]
        if args.get("role"):
            params["role"] = args["role"]
        if args.get("manufacturer"):
            params["manufacturer"] = args["manufacturer"]
        if args.get("status"):
            params["status"] = args["status"]
        if args.get("rack_id"):
            params["rack_id"] = args["rack_id"]
        if args.get("q"):
            params["q"] = args["q"]

        return await self._fetch_list(
            ctx,
            ENDPOINT,
            params=params,
            limit=args.get("limit", DEFAULT_LIMIT),
            offset=args.get("offset", 0),
        )
