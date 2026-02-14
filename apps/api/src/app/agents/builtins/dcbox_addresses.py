"""
DCBox — IP Addresses tool (NetBox /api/ipam/ip-addresses/)
"""
from __future__ import annotations
from typing import Any, Dict, ClassVar

from app.core.logging import get_logger
from app.agents.handlers.versioned_tool import tool_version, register_tool
from app.agents.context import ToolContext, ToolResult
from app.agents.builtins.dcbox_base import RemoteApiTool, DEFAULT_LIMIT

logger = get_logger(__name__)

ENDPOINT = "/api/ipam/ip-addresses/"

_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "address": {
            "type": "string",
            "description": "Filter by IP address (e.g. '10.0.0.1/24', '192.168.1.100')",
        },
        "parent": {
            "type": "string",
            "description": "Filter addresses within a parent prefix (e.g. '10.0.0.0/8')",
        },
        "device": {
            "type": "string",
            "description": "Filter by device name",
        },
        "interface": {
            "type": "string",
            "description": "Filter by interface name",
        },
        "vrf": {
            "type": "string",
            "description": "Filter by VRF name or ID",
        },
        "status": {
            "type": "string",
            "description": "Filter by status: active, reserved, deprecated, dhcp, slaac",
            "enum": ["active", "reserved", "deprecated", "dhcp", "slaac"],
        },
        "role": {
            "type": "string",
            "description": "Filter by role: loopback, secondary, anycast, vip, vrrp, hsrp, glbp, carp",
        },
        "tenant": {
            "type": "string",
            "description": "Filter by tenant slug",
        },
        "id": {
            "type": "integer",
            "description": "Get a single IP address by its ID",
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
                    "address": {"type": "string"},
                    "status": {"type": "object"},
                    "vrf": {"type": "object"},
                    "tenant": {"type": "object"},
                    "role": {"type": "object"},
                    "assigned_object": {"type": "object"},
                    "dns_name": {"type": "string"},
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
class DCBoxAddressesTool(RemoteApiTool):
    """Search and list IP addresses from DCBox (NetBox) IPAM module."""

    tool_slug: ClassVar[str] = "dcbox.addresses"
    tool_group: ClassVar[str] = "dcbox"
    name: ClassVar[str] = "DCBox IP Addresses"
    description: ClassVar[str] = (
        "Search and list IP addresses from DCBox/NetBox IPAM. "
        "Can filter by address, parent prefix, device, interface, VRF, status, role. "
        "Returns IP address details including assigned device/interface, DNS name, and status."
    )

    @tool_version(
        version="1.0.0",
        input_schema=_INPUT_SCHEMA,
        output_schema=_OUTPUT_SCHEMA,
        description="List and search IP addresses with filters",
    )
    async def v1_0_0(self, ctx: ToolContext, args: Dict[str, Any]) -> ToolResult:
        addr_id = args.get("id")
        if addr_id:
            return await self._fetch_detail(ctx, ENDPOINT, addr_id)

        params = {}
        if args.get("address"):
            params["address"] = args["address"]
        if args.get("parent"):
            params["parent"] = args["parent"]
        if args.get("device"):
            params["device"] = args["device"]
        if args.get("interface"):
            params["interface"] = args["interface"]
        if args.get("vrf"):
            params["vrf"] = args["vrf"]
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
