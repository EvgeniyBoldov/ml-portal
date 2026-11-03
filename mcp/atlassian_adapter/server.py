"""Atlassian profile of the shared Portal MCP adapter."""
from __future__ import annotations

import json
import logging
import os

from helpers.adapter_auth import AuthProfile
from helpers.adapter_policy import ToolPolicy
from helpers.mcp_adapter import AdapterConfig, MCPAdapter
from atlassian_adapter.source_runtime import PortalAtlassianAdapter, build_upstream_app

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
BROKER_TIMEOUT_SECONDS = int(os.environ.get("MCP_SECRET_BROKER_TIMEOUT_SECONDS", "10"))


def _build_app() -> MCPAdapter:
    from atlassian_adapter.diagnostics import AtlassianAuthDiagnostics

    # Uvicorn configures its own loggers; explicitly enable our safe diagnostics.
    for name in ("mcp.adapter", "mcp.adapter_auth", "mcp.credential_broker", "mcp.atlassian_auth"):
        logging.getLogger(name).setLevel(logging.INFO)
    upstream = AtlassianAuthDiagnostics(build_upstream_app())
    descriptors = dict(DEFAULT_RISK_DESCRIPTORS)
    configured_descriptors = json.loads(os.environ.get("MCP_ADAPTER_TOOL_DESCRIPTORS") or "{}")
    if not isinstance(configured_descriptors, dict):
        raise ValueError("MCP_ADAPTER_TOOL_DESCRIPTORS must be an object keyed by tool name")
    descriptors.update(configured_descriptors)
    return PortalAtlassianAdapter(AdapterConfig(
        name="portal-atlassian-mcp-adapter",
        policy=ToolPolicy(ENABLED_TOOLS, descriptors),
        auth_profile=AuthProfile(),
        timeout_s=float(os.environ.get("ATLASSIAN_MCP_TIMEOUT_SECONDS", "120")),
        broker_timeout_s=BROKER_TIMEOUT_SECONDS,
        allow_raw_credentials=False,
        discovery_headers={},
    ), upstream_app=upstream)


app = _build_app()
