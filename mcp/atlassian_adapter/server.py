"""Atlassian profile of the shared Portal MCP adapter."""
from __future__ import annotations

import json
import os
from typing import Any

from helpers.adapter_auth import AuthProfile, data_source_url, resolve_request_credential, upstream_auth_headers
from helpers.adapter_policy import ToolPolicy
from helpers.mcp_adapter import AdapterConfig, MCPAdapter

DEFAULT_TOOLS = "jira_search,jira_get_issue,jira_get_project_issues,confluence_search,confluence_get_page"
DEFAULT_RISK_DESCRIPTORS = {
    name: {"x-runtime": {"risk_level": "safe"}}
    for name in (
        "jira_search",
        "jira_get_issue",
        "jira_get_project_issues",
        "confluence_search",
        "confluence_get_page",
    )
}
ENABLED_TOOLS = frozenset(
    name.strip() for name in (os.environ.get("ATLASSIAN_MCP_ENABLED_TOOLS", "").strip() or DEFAULT_TOOLS).split(",")
    if name.strip()
)
ALLOW_RAW_CREDENTIALS = os.environ.get("MCP_ADAPTER_ALLOW_RAW_CREDENTIALS", "false").lower() == "true"
BROKER_TIMEOUT_SECONDS = int(os.environ.get("MCP_SECRET_BROKER_TIMEOUT_SECONDS", "10"))


async def _resolve_auth(params: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    args = params.get("arguments") or {}
    credential = await resolve_request_credential(args, timeout_s=BROKER_TIMEOUT_SECONDS, allow_raw=ALLOW_RAW_CREDENTIALS)
    tool = str(params.get("name") or "")
    return upstream_auth_headers(
        credential, profile=AuthProfile(kind="atlassian"), tool_name=tool,
        target_url=data_source_url(args, credential.payload, tool_name=tool),
    ), args


def _build_app() -> MCPAdapter:
    from mcp_atlassian.servers.main import main_mcp
    upstream = main_mcp.http_app(path="/mcp", stateless_http=True, transport="streamable-http")
    descriptors = dict(DEFAULT_RISK_DESCRIPTORS)
    configured_descriptors = json.loads(os.environ.get("MCP_ADAPTER_TOOL_DESCRIPTORS") or "{}")
    if not isinstance(configured_descriptors, dict):
        raise ValueError("MCP_ADAPTER_TOOL_DESCRIPTORS must be an object keyed by tool name")
    descriptors.update(configured_descriptors)
    return MCPAdapter(AdapterConfig(
        name="portal-atlassian-mcp-adapter",
        policy=ToolPolicy(ENABLED_TOOLS, descriptors),
        auth_profile=AuthProfile(kind="atlassian"),
        timeout_s=float(os.environ.get("ATLASSIAN_MCP_TIMEOUT_SECONDS", "120")),
        broker_timeout_s=BROKER_TIMEOUT_SECONDS,
        allow_raw_credentials=ALLOW_RAW_CREDENTIALS,
        discovery_headers={"Authorization": "Token broker-managed-placeholder"},
    ), upstream_app=upstream)


app = _build_app()
