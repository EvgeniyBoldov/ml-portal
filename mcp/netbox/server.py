from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import FastAPI, Header, HTTPException, Request, Response

from helpers.secret_broker import SecretBrokerClient, extract_credential_access


app = FastAPI(title="NetBox MCP Shim", version="1.0.0")

NETBOX_URL = os.environ.get("NETBOX_URL", "http://host.docker.internal:8000")
VERIFY_SSL = os.environ.get("VERIFY_SSL", "false").lower() == "true"
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("NETBOX_TIMEOUT_SECONDS", "20"))
BROKER_TIMEOUT_SECONDS = int(os.environ.get("MCP_SECRET_BROKER_TIMEOUT_SECONDS", "10"))
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "netbox-mcp-shim", "version": "1.0.0"}
SESSIONS: set[str] = set()


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

    # 4. Env fallback
    return _normalize_base_url(NETBOX_URL)


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
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, verify=VERIFY_SSL) as client:
        response = await client.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json()


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
                 "site", "rack", "role", "tenant", "primary_ip", "primary_ip4",
                 "region", "physical_address", "description", "comments",
                 "device_type", "platform", "serial", "asset_tag",
                 "vlan_group", "vid", "prefix", "family",
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
                            "description": "Get a single NetBox device by its exact hostname. Returns device details: role, site, rack, status, primary_ip, interfaces. Use when you know the exact device name.",
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
                            "description": "Search NetBox devices by name pattern or keyword. Returns list of matching devices with site, rack, role, status, primary IP. Use for partial name search or when listing devices in a location.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string", "description": "Search string matched against device name, description"},
                                    "limit": {"type": "integer", "default": 20, "description": "Max results (1-200)"},
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
                            "description": "List all sites (datacenters/offices) in NetBox. Returns site name, slug, status, region, physical_address, device count. Use to enumerate available locations before filtering devices by site.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "limit": {"type": "integer", "default": 50, "description": "Max results"},
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
                            "description": (
                                "Fetch objects from NetBox by type with optional filters. "
                                "object_type format: app.model. "
                                "Common types: dcim.device, dcim.site, dcim.rack, dcim.interface, dcim.cable, "
                                "ipam.ipaddress, ipam.prefix, ipam.vlan, ipam.vrf, "
                                "virtualization.virtualmachine, virtualization.vminterface, "
                                "dcim.devicerole, dcim.manufacturer, dcim.devicetype. "
                                "Common filters: site (slug), rack (name), role (slug), status (active/planned/staged/failed/decommissioning), "
                                "tenant (slug), tag (slug), q (search string), name (exact). "
                                "Example: object_type=dcim.device, filters={\"site\": \"dc1\", \"status\": \"active\"}"
                            ),
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "object_type": {"type": "string", "description": "NetBox object type in app.model format"},
                                    "filters": {"type": "object", "description": "Key-value filter pairs (site, rack, role, status, tag, q, name, etc.)"},
                                    "limit": {"type": "integer", "default": 50, "description": "Max results (1-200)"},
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
                            "description": (
                                "Full-text search across NetBox object types. "
                                "When object_types specified, queries each type endpoint with ?q= filter and returns combined results. "
                                "Without object_types uses NetBox global search (/api/extras/search/). "
                                "Useful for quick lookup when you don't know the exact type. "
                                "For targeted queries with filters prefer netbox_get_objects."
                            ),
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "q": {"type": "string", "description": "Search query string"},
                                    "object_types": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Optional object types to search (e.g. [\"dcim.device\", \"ipam.ipaddress\"]). Leave empty for global search.",
                                    },
                                    "limit": {"type": "integer", "default": 20, "description": "Max results per type"},
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
                    params={"q": query, "limit": max(1, min(limit, 200))},
                )
                return _jsonrpc_ok(rpc_id, _as_tool_result(data))

            if tool_name == "netbox_list_sites":
                limit = int(arguments.get("limit") or 50)
                data = await _netbox_get(
                    base_url=base_url,
                    token=token,
                    path="/api/dcim/sites/",
                    params={"limit": max(1, min(limit, 200))},
                )
                return _jsonrpc_ok(rpc_id, _as_tool_result(data))

            if tool_name == "netbox_get_objects":
                object_type = str(arguments.get("object_type") or "").strip()
                if not object_type or "." not in object_type:
                    raise ValueError("object_type must be in app.model format, e.g. dcim.device")
                app, model = object_type.split(".", 1)
                limit = int(arguments.get("limit") or 50)
                filters = arguments.get("filters") or {}
                params: Dict[str, Any] = {"limit": max(1, min(limit, 200))}
                params.update({k: v for k, v in filters.items() if v is not None})
                # NetBox REST path: pluralize model name (interfaces, addresses, etc.)
                model_path = model.replace("_", "-")
                # Handle irregular plurals
                if model_path.endswith("address"):
                    model_path += "es"
                elif model_path.endswith("s"):
                    pass  # already plural
                else:
                    model_path += "s"
                data = await _netbox_get(
                    base_url=base_url,
                    token=token,
                    path=f"/api/{app}/{model_path}/",
                    params=params,
                )
                return _jsonrpc_ok(rpc_id, _as_tool_result(data))

            if tool_name == "netbox_search_objects":
                q = str(arguments.get("q") or "").strip()
                object_types = arguments.get("object_types") or []
                limit = int(arguments.get("limit") or 20)
                if object_types:
                    results = []
                    for ot in object_types[:5]:
                        if "." not in ot:
                            continue
                        app, model = ot.split(".", 1)
                        params: Dict[str, Any] = {"limit": max(1, min(limit, 100))}
                        if q:
                            params["q"] = q
                        try:
                            page = await _netbox_get(
                                base_url=base_url,
                                token=token,
                                path=f"/api/{app}/{model.replace('_', '-')}s/",
                                params=params,
                            )
                            results.append({"object_type": ot, "results": page.get("results", []), "count": page.get("count", 0)})
                        except Exception:
                            pass
                    return _jsonrpc_ok(rpc_id, _as_tool_result({"results": results}))
                else:
                    data = await _netbox_get(
                        base_url=base_url,
                        token=token,
                        path="/api/extras/search/",
                        params={"q": q, "limit": max(1, min(limit, 100))},
                    )
                    return _jsonrpc_ok(rpc_id, _as_tool_result(data))

            return _jsonrpc_err(rpc_id, -32005, f"Tool '{tool_name}' not found")

        return _jsonrpc_err(rpc_id, -32601, f"Method '{method}' not found")
    except ValueError as exc:
        return _jsonrpc_ok(
            rpc_id,
            {"content": [{"type": "text", "text": str(exc)}], "isError": True},
        )
    except httpx.HTTPStatusError as exc:
        message = f"NetBox HTTP {exc.response.status_code}: {exc.response.text[:500]}"
        return _jsonrpc_ok(
            rpc_id,
            {"content": [{"type": "text", "text": message}], "isError": True},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
