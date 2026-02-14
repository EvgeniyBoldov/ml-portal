"""
DCBox — IP Prefixes tool (NetBox /api/ipam/prefixes/)
"""
from __future__ import annotations
from typing import Any, Dict, ClassVar

from app.core.logging import get_logger
from app.agents.handlers.versioned_tool import tool_version, register_tool
from app.agents.context import ToolContext, ToolResult
from app.agents.builtins.dcbox_base import RemoteApiTool, DEFAULT_LIMIT

logger = get_logger(__name__)

ENDPOINT = "/api/ipam/prefixes/"

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "prefix": {
            "type": "string",
            "description": "Filter by prefix (e.g. '10.0.0.0/8', '192.168.1.0/24')",
        },
        "within": {
            "type": "string",
            "description": "Filter prefixes within a given parent prefix (e.g. '10.0.0.0/8')",
        },
        "site": {
            "type": "string",
            "description": "Filter by site slug",
        },
        "vrf": {
            "type": "string",
            "description": "Filter by VRF name or ID",
        },
        "vlan_id": {
            "type": "integer",
            "description": "Filter by VLAN ID",
        },
        "status": {
            "type": "string",
            "description": "Filter by status: active, container, reserved, deprecated",
            "enum": ["active", "container", "reserved", "deprecated"],
        },
        "role": {
            "type": "string",
            "description": "Filter by role slug",
        },
        "tenant": {
            "type": "string",
            "description": "Filter by tenant slug",
        },
        "id": {
            "type": "integer",
            "description": "Get a single prefix by its ID",
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
                    "prefix": {"type": "string"},
                    "status": {"type": "object"},
                    "site": {"type": "object"},
                    "vrf": {"type": "object"},
                    "vlan": {"type": "object"},
                    "role": {"type": "object"},
                    "tenant": {"type": "object"},
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
class DCBoxPrefixesTool(RemoteApiTool):
    """Search and list IP prefixes from DCBox (NetBox) IPAM module."""

    tool_slug: ClassVar[str] = "dcbox.prefixes"
    tool_group: ClassVar[str] = "dcbox"
    name: ClassVar[str] = "DCBox IP Prefixes"
    description: ClassVar[str] = (
        "Search and list IP prefixes (subnets) from DCBox/NetBox IPAM. "
        "Can filter by prefix, parent prefix (within), site, VRF, VLAN, status, role. "
        "Returns prefix details including VLAN, VRF, site, and utilization."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        description="List and search IP prefixes with filters",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        prefix_id = args.get("id")
        if prefix_id:
            return await self._fetch_detail(ctx, ENDPOINT, prefix_id)

        params = {}
        if args.get("prefix"):
            params["prefix"] = args["prefix"]
        if args.get("within"):
            params["within"] = args["within"]
        if args.get("site"):
            params["site"] = args["site"]
        if args.get("vrf"):
            params["vrf"] = args["vrf"]
        if args.get("vlan_id"):
            params["vlan_id"] = args["vlan_id"]
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
