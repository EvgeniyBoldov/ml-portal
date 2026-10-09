from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response

from helpers.secret_broker import SecretBrokerClient, extract_credential_access


app = FastAPI(title="NetBox MCP Shim", version="1.0.0")

VERIFY_SSL = os.environ.get("VERIFY_SSL", "false").lower() == "true"
NETBOX_CA_BUNDLE = (os.environ.get("NETBOX_CA_BUNDLE") or "").strip()
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("NETBOX_TIMEOUT_SECONDS", "20"))
BROKER_TIMEOUT_SECONDS = int(os.environ.get("MCP_SECRET_BROKER_TIMEOUT_SECONDS", "10"))
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "netbox-mcp-shim", "version": "1.0.0"}
SESSIONS: set[str] = set()

# Explicit routes for NetBox plugins.  Keys are stable MCP object types; values
# are relative API paths so the registry cannot redirect requests to another
# host.  Keep endpoint spelling here even when it is non-standard (for
# example, DCBox exposes ``capacitys`` and ``vlanmappinggroup``).
PLUGIN_ENDPOINTS = {
    "plugin.installed_plugins": "/api/plugins/installed-plugins/",
    "plugin.dcbox": "/api/plugins/dcbox/",
    "plugin.technical_record": "/api/plugins/technical-record/",
    "plugin.techsupport": "/api/plugins/techsupport/",
    "plugin.netbox_attachments": "/api/plugins/netbox-attachments/",
    "plugin.change_requests": "/api/plugins/change-requests/",
    "plugin.storage_systems": "/api/plugins/storage-systems/",
    "plugin.operation_system": "/api/plugins/operation-system/",
    "plugin.backup": "/api/plugins/backup/",
    "plugin.aggregate": "/api/plugins/aggregate/",
    "plugin.custom_objects": "/api/plugins/custom-objects/",
    "plugin.floorplan": "/api/plugins/floorplan/",
    "dcbox.capacity": "/api/plugins/dcbox/capacitys/",
    "dcbox.channel": "/api/plugins/dcbox/channels/",
    "dcbox.device_group": "/api/plugins/dcbox/device-groups/",
    "dcbox.infrastructure_place": "/api/plugins/dcbox/infrastructure-places/",
    "dcbox.interface_group": "/api/plugins/dcbox/interface-groups/",
    "dcbox.prefix_group": "/api/plugins/dcbox/prefix-groups/",
    "dcbox.vlan_mapping_group": "/api/plugins/dcbox/vlanmappinggroup/",
}

# DCBox does not expose NetBox's optional global ``/api/extras/search/``
# endpoint.  A type-less search must therefore be expanded into a bounded set
# of vanilla NetBox resources instead of assuming that the extras app exists.
# Plugin resources are intentionally not included here: callers must name a
# plugin object type explicitly, which is then resolved through
# ``PLUGIN_ENDPOINTS`` above.
DEFAULT_SEARCH_OBJECT_TYPES = (
    "dcim.device",
    "dcim.rack",
    "dcim.site",
    "ipam.ipaddress",
    "ipam.prefix",
)

# NetBox API slugs are not reliably derived from Django model names by adding
# an "s". Keep the documented inventory types explicit so a typo cannot make
# an IPAM lookup look like an empty search result.
OBJECT_ENDPOINTS = {
    "dcim.device": "/api/dcim/devices/",
    "dcim.site": "/api/dcim/sites/",
    "dcim.rack": "/api/dcim/racks/",
    "dcim.interface": "/api/dcim/interfaces/",
    "dcim.cable": "/api/dcim/cables/",
    "dcim.devicerole": "/api/dcim/device-roles/",
    "dcim.manufacturer": "/api/dcim/manufacturers/",
    "dcim.devicetype": "/api/dcim/device-types/",
    "ipam.ipaddress": "/api/ipam/ip-addresses/",
    "ipam.prefix": "/api/ipam/prefixes/",
    "ipam.vlan": "/api/ipam/vlans/",
    "ipam.vrf": "/api/ipam/vrfs/",
    "virtualization.virtualmachine": "/api/virtualization/virtual-machines/",
    "virtualization.vminterface": "/api/virtualization/interfaces/",
}


def _jsonrpc_ok(rpc_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _jsonrpc_err(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _normalize_base_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    # Handle full URLs and plain host/path values uniformly.
    if parsed.scheme and parsed.netloc:
        path = (parsed.path or "").rstrip("/")
        # Operators often store NetBox URL as ".../api/".
        # Tool paths below already include "/api/...", so trim the suffix here.
        if path.endswith("/api"):
            path = path[:-4]
        normalized = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                path.rstrip("/"),
                "",  # params
                parsed.query,
                "",  # fragment
            )
        )
        return normalized.rstrip("/")

    plain = raw.rstrip("/")
    if plain.endswith("/api"):
        plain = plain[:-4]
    return plain.rstrip("/")


def _extract_token(payload: Dict[str, Any]) -> str:
    for key in ("token", "api_token", "api_key", "access_token"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError(
        "Resolved credential payload does not contain token "
        "(expected one of: token, api_token, api_key, access_token)"
    )


def _extract_base_url(payload: Dict[str, Any], arguments: Dict[str, Any]) -> str:
    # 1. Credential payload takes highest priority (broker may return netbox_url)
    for key in ("netbox_url", "base_url", "url"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_base_url(value)

    # 2. Explicit argument
    for key in ("netbox_url", "base_url", "url"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_base_url(value)

    # 3. Instance context injected by operation executor
    instance_context = arguments.get("instance_context")
    if isinstance(instance_context, dict):
        # data_instance_url is set from tool_instances.url
        for key in ("data_instance_url", "provider_url", "base_url"):
            value = instance_context.get(key)
            if isinstance(value, str) and value.strip():
                return _normalize_base_url(value)
        # config.url is the raw config dict from the data instance
        config = instance_context.get("config")
        if isinstance(config, dict):
            for key in ("url", "base_url", "netbox_url"):
                value = config.get(key)
                if isinstance(value, str) and value.strip():
                    return _normalize_base_url(value)

    raise ValueError(
        "No NetBox base URL: expected one of "
        "payload.{netbox_url|base_url|url}, arguments.{netbox_url|base_url|url}, "
        "instance_context.{data_instance_url|provider_url|base_url}, or instance_context.config.url"
    )


async def _resolve_runtime_access(arguments: Dict[str, Any]) -> tuple[str, str]:
    # Priority 1: broker-based short-lived token (MCP_CREDENTIAL_BROKER_ENABLED=true)
    access = extract_credential_access(arguments)
    if access:
        broker = SecretBrokerClient(timeout_s=BROKER_TIMEOUT_SECONDS)
        resolved = await broker.resolve(access)
        token = _extract_token(resolved.payload)
        base_url = _extract_base_url(resolved.payload, arguments)
        return base_url, token

    # Priority 2: legacy credentials payload injected via instance_context.credentials
    # (used when MCP_CREDENTIAL_BROKER_ENABLED=false, executor injects decrypted payload)
    instance_context = arguments.get("instance_context")
    if isinstance(instance_context, dict):
        creds = instance_context.get("credentials")
        if isinstance(creds, dict):
            try:
                token = _extract_token(creds)
                base_url = _extract_base_url(creds, arguments)
                return base_url, token
            except ValueError:
                pass

    # Priority 3: explicit token argument (dev/test only)
    token = str(arguments.get("token") or arguments.get("api_token") or "").strip()
    if token:
        base_url = _extract_base_url({}, arguments)
        return base_url, token

    raise ValueError(
        "No NetBox credentials: expected credential_access (broker), "
        "instance_context.credentials (legacy), or explicit token argument"
    )


async def _netbox_get(
    *,
    base_url: str,
    token: str,
    path: str,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
    }
    url = f"{base_url}{path}"
    verify: bool | str = NETBOX_CA_BUNDLE if NETBOX_CA_BUNDLE else VERIFY_SSL
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, verify=verify) as client:
        response = await client.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


def _resolve_object_path(object_type: str) -> str:
    """Resolve a canonical object type to a safe NetBox API path."""
    normalized = str(object_type or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*", normalized):
        raise ValueError("object_type must be in app.model format, e.g. dcim.device")

    plugin_path = PLUGIN_ENDPOINTS.get(normalized)
    if plugin_path:
        return plugin_path

    standard_path = OBJECT_ENDPOINTS.get(normalized)
    if standard_path:
        return standard_path

    if normalized.startswith("dcbox."):
        raise ValueError(f"Unknown DCBox object type: {normalized}")

    app_name, model = normalized.split(".", 1)
    model_path = model.replace("_", "-")
    if model_path.endswith("address"):
        model_path += "es"
    elif not model_path.endswith("s"):
        model_path += "s"
    return f"/api/{app_name}/{model_path}/"


def _search_object_types(object_types: Any) -> list[str]:
    """Return explicit types for a bounded generic NetBox search."""
    if not object_types:
        return list(DEFAULT_SEARCH_OBJECT_TYPES)
    if not isinstance(object_types, list):
        raise ValueError("object_types must be an array of app.model values")
    selected = [str(object_type).strip() for object_type in object_types if str(object_type).strip()]
    if len(selected) > 5:
        raise ValueError("netbox_search_objects supports at most five object_types per call")
    return selected


def _page_offset(arguments: Dict[str, Any]) -> int:
    offset = int(arguments.get("offset") or 0)
    if offset < 0:
        raise ValueError("offset must be non-negative")
    return offset


def _slim_result(obj: Any, max_results: int = 50) -> Any:
    """Trim deep nested objects and limit result list size to keep LLM context lean."""
    if isinstance(obj, list):
        return [_slim_result(item) for item in obj[:max_results]]
    if not isinstance(obj, dict):
        return obj
    slim = {}
    for k, v in obj.items():
        # Keep display_url at top level so LLM can reference it
        if k in ("id", "url", "display_url", "display", "name", "slug", "status",
                 "count", "next", "previous", "results", "object_type",
                 "searched_types", "errors", "error", "truncated",
                 "site", "rack", "role", "tenant", "primary_ip", "primary_ip4",
                 "region", "physical_address", "description", "comments",
                 "device_type", "platform", "serial", "asset_tag",
                 "vlan_group", "vid", "prefix", "family", "address",
                 "vrf", "vlan", "scope", "assigned_object", "dns_name",
                 "gateway", "utilization", "tags", "custom_fields",
                 "vcpus", "memory", "disk", "cluster"):
            if isinstance(v, dict):
                # Flatten nested objects to {id, name, slug, url}
                slim[k] = {sk: sv for sk, sv in v.items() if sk in ("id", "name", "slug", "url", "display_url", "display", "label", "value")}
            else:
                slim[k] = v
    return slim


def _as_tool_result(data: Dict[str, Any]) -> Dict[str, Any]:
    # Slim down for LLM but keep full data in structuredContent
    results = data.get("results")
    if isinstance(results, list):
        slimmed = {"count": data.get("count", len(results)), "results": _slim_result(results)}
        for key in ("errors", "searched_types"):
            if key in data:
                slimmed[key] = _slim_result(data[key])
    else:
        slimmed = _slim_result(data)
    return {
        "content": [{"type": "text", "text": json.dumps(slimmed, ensure_ascii=False, indent=2)}],
        "structuredContent": data,
        "isError": False,
    }


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/")
async def mcp_root(
    request: Request,
    response: Response,
    mcp_session_id: str | None = Header(default=None),
) -> dict[str, Any]:
    payload = await request.json()
    rpc_id = payload.get("id")
    method = payload.get("method")
    params = payload.get("params") or {}

    try:
        if method == "initialize":
            session_id = str(uuid.uuid4())
            SESSIONS.add(session_id)
            response.headers["mcp-session-id"] = session_id
            return _jsonrpc_ok(
                rpc_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                    "serverInfo": SERVER_INFO,
                    "instructions": "NetBox MCP shim with short-lived credential access support.",
                },
            )

        if not mcp_session_id or mcp_session_id not in SESSIONS:
            return _jsonrpc_err(rpc_id, -32002, "Session not initialized")

        if method == "tools/list":
            return _jsonrpc_ok(
                rpc_id,
                {
                    "tools": [
                        {
                            "name": "netbox_get_device",
                            "description": "Get a device by its exact name.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Exact device hostname as stored in NetBox"},
                                },
                                "required": ["name"],
                            },
                            "annotations": {
                                "readOnlyHint": True,
                                "destructiveHint": False,
                                "idempotentHint": True,
                            },
                        },
                        {
                            "name": "netbox_search_devices",
                            "description": "Search device names and descriptions by non-empty text.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "Search string matched against device name, description"},
                                    "limit": {"type": "integer", "default": 20, "description": "Max results (1-200)"},
                                    "offset": {"type": "integer", "minimum": 0, "default": 0, "description": "Page offset"},
                                },
                                "required": ["query"],
                            },
                            "annotations": {
                                "readOnlyHint": True,
                                "destructiveHint": False,
                                "idempotentHint": True,
                            },
                        },
                        {
                            "name": "netbox_list_sites",
                            "description": "List a page of sites with count and next-page metadata.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
                                    "offset": {"type": "integer", "minimum": 0, "default": 0, "description": "Page offset"},
                                },
                            },
                            "annotations": {
                                "readOnlyHint": True,
                                "destructiveHint": False,
                                "idempotentHint": True,
                            },
                        },
                        {
                            "name": "netbox_get_objects",
                            "description": "List a page of one NetBox object type, optionally filtered. Nested attributes remain in the records.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "object_type": {"type": "string", "description": "NetBox object type, e.g. ipam.prefix or dcim.device"},
                                    "filters": {"type": "object", "description": "NetBox API query filters for this type; e.g. prefix for ipam.prefix, address for ipam.ipaddress, device for dcim.interface, site/status for dcim.device"},
                                    "limit": {"type": "integer", "default": 50, "description": "Max results (1-200)"},
                                    "offset": {"type": "integer", "minimum": 0, "default": 0, "description": "Page offset; advance when next is present"},
                                },
                                "required": ["object_type"],
                            },
                            "annotations": {
                                "readOnlyHint": True,
                                "destructiveHint": False,
                                "idempotentHint": True,
                            },
                        },
                        {
                            "name": "netbox_search_objects",
                            "description": "Search up to five NetBox object types by non-empty text. Returns matching records and per-type errors.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "q": {"type": "string", "minLength": 1, "pattern": "\\S", "description": "Non-empty text matched inside the selected object types"},
                                    "object_types": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "At most five object types, e.g. ipam.prefix and ipam.ipaddress; omitted means the five default types",
                                    },
                                    "limit": {"type": "integer", "default": 20, "description": "Max results per type"},
                                    "offset": {"type": "integer", "minimum": 0, "default": 0, "description": "Page offset applied to each type"},
                                },
                                "required": ["q"],
                            },
                            "annotations": {
                                "readOnlyHint": True,
                                "destructiveHint": False,
                                "idempotentHint": True,
                            },
                        },
                    ]
                },
            )

        if method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments") or {}
            base_url, token = await _resolve_runtime_access(arguments)

            if tool_name == "netbox_get_device":
                name = str(arguments.get("name") or "").strip()
                if not name:
                    raise ValueError("name is required")
                data = await _netbox_get(
                    base_url=base_url,
                    token=token,
                    path="/api/dcim/devices/",
                    params={"name": name, "limit": 1},
                )
                return _jsonrpc_ok(rpc_id, _as_tool_result(data))

            if tool_name == "netbox_search_devices":
                query = str(arguments.get("query") or "").strip()
                if not query:
                    raise ValueError("query is required")
                limit = int(arguments.get("limit") or 20)
                data = await _netbox_get(
                    base_url=base_url,
                    token=token,
                    path="/api/dcim/devices/",
                    params={"q": query, "limit": max(1, min(limit, 200)), "offset": _page_offset(arguments)},
                )
                return _jsonrpc_ok(rpc_id, _as_tool_result(data))

            if tool_name == "netbox_list_sites":
                limit = int(arguments.get("limit") or 50)
                data = await _netbox_get(
                    base_url=base_url,
                    token=token,
                    path="/api/dcim/sites/",
                    params={"limit": max(1, min(limit, 200)), "offset": _page_offset(arguments)},
                )
                return _jsonrpc_ok(rpc_id, _as_tool_result(data))

            if tool_name == "netbox_get_objects":
                object_type = str(arguments.get("object_type") or "").strip()
                if not object_type or "." not in object_type:
                    raise ValueError("object_type must be in app.model format, e.g. dcim.device")
                limit = int(arguments.get("limit") or 50)
                offset = _page_offset(arguments)
                filters = arguments.get("filters") or {}
                if not isinstance(filters, dict):
                    raise ValueError("filters must be an object")
                params: Dict[str, Any] = {k: v for k, v in filters.items() if v is not None and k not in {"limit", "offset"}}
                params.update({"limit": max(1, min(limit, 200)), "offset": offset})
                data = await _netbox_get(
                    base_url=base_url,
                    token=token,
                    path=_resolve_object_path(object_type),
                    params=params,
                )
                return _jsonrpc_ok(rpc_id, _as_tool_result(data))

            if tool_name == "netbox_search_objects":
                q = str(arguments.get("q") or "").strip()
                if not q:
                    raise ValueError("q is required")
                object_types = _search_object_types(arguments.get("object_types"))
                limit = int(arguments.get("limit") or 20)
                offset = _page_offset(arguments)
                results = []
                errors = []
                for ot in object_types:
                    params: Dict[str, Any] = {"limit": max(1, min(limit, 100)), "offset": offset}
                    if q:
                        params["q"] = q
                    try:
                        path = _resolve_object_path(ot)
                        page = await _netbox_get(
                            base_url=base_url,
                            token=token,
                            path=path,
                            params=params,
                        )
                        results.append({"object_type": ot, "results": page.get("results", []), "count": page.get("count", 0), "next": page.get("next")})
                    except httpx.HTTPStatusError as exc:
                        errors.append({"object_type": ot, "status": exc.response.status_code, "error": "NetBox HTTP error"})
                    except (httpx.RequestError, ValueError) as exc:
                        errors.append({"object_type": ot, "error": type(exc).__name__})
                data = {"results": results, "errors": errors, "searched_types": object_types}
                if not results:
                    return _jsonrpc_ok(rpc_id, {
                        "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}],
                        "structuredContent": data,
                        "isError": True,
                    })
                return _jsonrpc_ok(rpc_id, _as_tool_result(data))

            return _jsonrpc_err(rpc_id, -32005, f"Tool '{tool_name}' not found")

        return _jsonrpc_err(rpc_id, -32601, f"Method '{method}' not found")
    except ValueError as exc:
        return _jsonrpc_ok(
            rpc_id,
            {"content": [{"type": "text", "text": str(exc)}], "isError": True},
        )
    except httpx.HTTPStatusError as exc:
        message = f"NetBox HTTP {exc.response.status_code} at {exc.request.url.path}; query failed, not an empty result"
        return _jsonrpc_ok(
            rpc_id,
            {"content": [{"type": "text", "text": message}], "isError": True},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
