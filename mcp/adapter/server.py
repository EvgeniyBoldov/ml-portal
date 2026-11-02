"""Configurable gateway for external HTTP MCP servers."""
from __future__ import annotations

import json
import os

from helpers.adapter_auth import AuthProfile
from helpers.adapter_policy import ToolPolicy
from helpers.mcp_adapter import AdapterConfig, MCPAdapter


def build_app() -> MCPAdapter:
    enabled = os.environ.get("MCP_ADAPTER_ENABLED_TOOLS", "").strip()
    descriptors = json.loads(os.environ.get("MCP_ADAPTER_TOOL_DESCRIPTORS") or "{}")
    if not isinstance(descriptors, dict) or any(not isinstance(v, dict) for v in descriptors.values()):
        raise ValueError("Tool descriptors must be an object keyed by tool name")
    return MCPAdapter(AdapterConfig(
        upstream_url=os.environ["MCP_ADAPTER_UPSTREAM_URL"],
        name=os.environ.get("MCP_ADAPTER_NAME", "portal-mcp-adapter"),
        policy=ToolPolicy(
            enabled_tools=None if enabled == "*" else frozenset(t.strip() for t in enabled.split(",") if t.strip()),
            descriptors=descriptors,
        ),
        auth_profile=AuthProfile(
            kind=os.environ.get("MCP_ADAPTER_AUTH_PROFILE", "standard"),
            token_header=os.environ.get("MCP_ADAPTER_TOKEN_HEADER", "Authorization"),
            token_scheme=os.environ.get("MCP_ADAPTER_TOKEN_SCHEME", "Bearer"),
            api_key_header=os.environ.get("MCP_ADAPTER_API_KEY_HEADER", "X-API-Key"),
            target_url_header=os.environ.get("MCP_ADAPTER_TARGET_URL_HEADER", ""),
        ),
        timeout_s=float(os.environ.get("MCP_ADAPTER_TIMEOUT_SECONDS", "120")),
        broker_timeout_s=int(os.environ.get("MCP_SECRET_BROKER_TIMEOUT_SECONDS", "10")),
        session_ttl_s=int(os.environ.get("MCP_ADAPTER_SESSION_TTL_SECONDS", "3600")),
        max_request_bytes=int(os.environ.get("MCP_ADAPTER_MAX_REQUEST_BYTES", "262144")),
        max_response_bytes=int(os.environ.get("MCP_ADAPTER_MAX_RESPONSE_BYTES", "1048576")),
        verify_ssl=os.environ.get("MCP_ADAPTER_CA_BUNDLE") or os.environ.get("VERIFY_SSL", "true").lower() == "true",
        allow_raw_credentials=os.environ.get("MCP_ADAPTER_ALLOW_RAW_CREDENTIALS", "false").lower() == "true",
    ))


app = build_app()
