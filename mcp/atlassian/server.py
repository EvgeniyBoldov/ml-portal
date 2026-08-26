from __future__ import annotations

import base64
import json
import logging
import os
import re
import uuid
from typing import Any, Dict
from urllib.parse import quote, urlparse, urlunparse

import httpx
from fastapi import FastAPI, Header, Request, Response

from helpers.secret_broker import SecretBrokerClient, extract_credential_access


app = FastAPI(title="Atlassian Jira MCP Shim", version="1.0.0")
logger = logging.getLogger("mcp.atlassian.jira")

VERIFY_SSL = os.environ.get("VERIFY_SSL", "true").lower() == "true"
JIRA_CA_BUNDLE = (os.environ.get("JIRA_CA_BUNDLE") or "").strip()
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("JIRA_TIMEOUT_SECONDS", "20"))
BROKER_TIMEOUT_SECONDS = int(os.environ.get("MCP_SECRET_BROKER_TIMEOUT_SECONDS", "10"))
MAX_RESULTS = int(os.environ.get("JIRA_MCP_MAX_RESULTS", "50"))
PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "atlassian-jira-mcp-shim", "version": "1.0.0"}
SESSIONS: set[str] = set()

_SECRET_VALUE_RE = re.compile(
    r"(?i)(authorization|token|pat|api[_-]?token|access[_-]?token|api[_-]?key|password|secret)"
    r"(\s*[\"']?\s*[:=]\s*)(?:[\"'][^\"']*[\"']|(?:bearer|basic)\s+[^\s,;]+|[^\s,;]+)"
)


def _safe_error_message(exc: BaseException) -> str:
    """Make an operator-useful error safe for container logs."""
    message = str(exc).replace("\n", " ").replace("\r", " ")
    redacted = _SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}***", message)
    return redacted[:500]


def _jsonrpc_ok(rpc_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "result": result}


def _jsonrpc_err(rpc_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "error": {"code": code, "message": message}}


def _normalize_base_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return raw.rstrip("/")
    path = (parsed.path or "").rstrip("/")
    for suffix in ("/rest/api/3", "/rest/api/2", "/rest/api"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break
    return urlunparse((parsed.scheme, parsed.netloc, path.rstrip("/"), "", "", "")).rstrip("/")


def _extract_base_url(payload: Dict[str, Any], arguments: Dict[str, Any]) -> str:
    for source in (payload, arguments):
        for key in ("jira_url", "base_url", "url"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return _normalize_base_url(value)
    instance_context = arguments.get("instance_context")
    if isinstance(instance_context, dict):
        for key in ("data_instance_url", "provider_url", "base_url"):
            value = instance_context.get(key)
            if isinstance(value, str) and value.strip():
                return _normalize_base_url(value)
        config = instance_context.get("config")
        if isinstance(config, dict):
            for key in ("jira_url", "base_url", "url"):
                value = config.get(key)
                if isinstance(value, str) and value.strip():
                    return _normalize_base_url(value)
    raise ValueError("No Jira base URL configured")


def _extract_auth(payload: Dict[str, Any]) -> dict[str, str]:
    token = next((str(payload[key]).strip() for key in ("token", "pat", "api_token", "access_token") if payload.get(key)), "")
    if token:
        return {"Authorization": f"Bearer {token}"}
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "").strip()
    if username and password:
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    raise ValueError("Resolved credential payload has no Jira PAT or basic credentials")


async def _resolve_runtime_access(arguments: Dict[str, Any]) -> tuple[str, dict[str, str]]:
    access = extract_credential_access(arguments)
    if access:
        resolved = await SecretBrokerClient(timeout_s=BROKER_TIMEOUT_SECONDS).resolve(access)
        logger.info(
            "jira_mcp_credentials_resolved source=broker auth_type=%s owner_type=%s credential_id=%s",
            resolved.auth_type or "unknown",
            resolved.owner_type or "unknown",
            resolved.credential_id or "unknown",
        )
        return _extract_base_url(resolved.payload, arguments), _extract_auth(resolved.payload)

    instance_context = arguments.get("instance_context")
    if isinstance(instance_context, dict) and isinstance(instance_context.get("credentials"), dict):
        logger.warning("jira_mcp_credentials_resolved source=legacy_raw_payload")
        credentials = instance_context["credentials"]
        return _extract_base_url(credentials, arguments), _extract_auth(credentials)
    raise ValueError("No Jira credentials: expected broker credential_access or legacy instance_context.credentials")


def _limit(value: Any, default: int = 20) -> int:
    try:
        requested = int(value or default)
    except (TypeError, ValueError):
        requested = default
    return max(1, min(requested, MAX_RESULTS))


def _issue_path_key(value: Any) -> str:
    key = str(value or "").strip()
    if not key:
        raise ValueError("issue_key is required")
    return quote(key, safe="")


async def _jira_request(
    *,
    base_url: str,
    headers: dict[str, str],
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    verify: bool | str = JIRA_CA_BUNDLE if JIRA_CA_BUNDLE else VERIFY_SSL
    request_headers = {"Accept": "application/json", **headers}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, verify=verify) as client:
        response = await client.request(
            method,
            f"{base_url}{path}",
            headers=request_headers,
            params=params,
            json=body,
        )
    if response.status_code >= 400:
        raise ValueError(f"Jira request failed with HTTP {response.status_code}")
    if response.status_code == 204 or not response.content:
        return {"ok": True}
    return response.json()


def _bounded_issue(issue: Any) -> Any:
    if not isinstance(issue, dict):
        return issue
    fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
    return {
        "id": issue.get("id"),
        "key": issue.get("key"),
        "self": issue.get("self"),
        "fields": {
            key: fields.get(key)
            for key in (
                "summary",
                "description",
                "status",
                "issuetype",
                "project",
                "priority",
                "assignee",
                "reporter",
                "labels",
                "updated",
                "created",
            )
            if key in fields
        },
    }


def _tool_result(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and isinstance(data.get("issues"), list):
        display: Any = {"issues": [_bounded_issue(issue) for issue in data["issues"][:MAX_RESULTS]], "total": data.get("total")}
    elif isinstance(data, dict) and "key" in data and "fields" in data:
        display = _bounded_issue(data)
    else:
        display = data
    return {
        "content": [{"type": "text", "text": json.dumps(display, ensure_ascii=False)}],
        "structuredContent": display,
        "isError": False,
    }


def _tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str] | None = None,
    *,
    read_only: bool,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
        "annotations": {
            "readOnlyHint": read_only,
            "destructiveHint": False,
            "idempotentHint": read_only,
        },
    }


TOOLS = [
    _tool(
        "jira_search_issues",
        "Search Jira issues with JQL. Results are bounded.",
        {"jql": {"type": "string"}, "limit": {"type": "integer", "default": 20}},
        ["jql"],
        read_only=True,
    ),
    _tool(
        "jira_get_issue",
        "Get one Jira issue by key.",
        {"issue_key": {"type": "string"}},
        ["issue_key"],
        read_only=True,
    ),
    _tool(
        "jira_list_projects",
        "List visible Jira projects.",
        {"limit": {"type": "integer", "default": 50}},
        read_only=True,
    ),
    _tool(
        "jira_create_issue",
        "Create a Jira issue. Requires project_key, issue_type and summary.",
        {
            "project_key": {"type": "string"},
            "issue_type": {"type": "string"},
            "summary": {"type": "string"},
            "description": {"type": "string"},
            "labels": {"type": "array", "items": {"type": "string"}},
        },
        ["project_key", "issue_type", "summary"],
        read_only=False,
    ),
    _tool(
        "jira_update_issue",
        "Update supplied Jira issue fields.",
        {"issue_key": {"type": "string"}, "fields": {"type": "object"}},
        ["issue_key", "fields"],
        read_only=False,
    ),
    _tool(
        "jira_transition_issue",
        "Transition an issue using its Jira transition id.",
        {"issue_key": {"type": "string"}, "transition_id": {"type": "string"}},
        ["issue_key", "transition_id"],
        read_only=False,
    ),
    _tool(
        "jira_add_comment",
        "Add a plain-text comment to a Jira issue.",
        {"issue_key": {"type": "string"}, "body": {"type": "string"}},
        ["issue_key", "body"],
        read_only=False,
    ),
]


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
    rpc_id, method, params = payload.get("id"), payload.get("method"), payload.get("params") or {}
    try:
        if method == "initialize":
            session_id = str(uuid.uuid4())
            SESSIONS.add(session_id)
            response.headers["mcp-session-id"] = session_id
            return _jsonrpc_ok(
                rpc_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": SERVER_INFO,
                    "instructions": (
                        "Jira Server/Data Center MCP shim using short-lived "
                        "credential broker access."
                    ),
                },
            )
        if not mcp_session_id or mcp_session_id not in SESSIONS:
            return _jsonrpc_err(rpc_id, -32002, "Session not initialized")
        if method == "tools/list":
            return _jsonrpc_ok(rpc_id, {"tools": TOOLS})
        if method != "tools/call":
            return _jsonrpc_err(rpc_id, -32601, f"Method not found: {method}")
        tool_name, arguments = params.get("name"), params.get("arguments") or {}
        base_url, auth_headers = await _resolve_runtime_access(arguments)
        if tool_name == "jira_search_issues":
            jql = str(arguments.get("jql") or "").strip()
            if not jql:
                raise ValueError("jql is required")
            data = await _jira_request(base_url=base_url, headers=auth_headers, method="GET", path="/rest/api/2/search", params={"jql": jql, "maxResults": _limit(arguments.get("limit")), "fields": "summary,description,status,issuetype,project,priority,assignee,reporter,labels,updated,created"})
        elif tool_name == "jira_get_issue":
            key = _issue_path_key(arguments.get("issue_key"))
            data = await _jira_request(
                base_url=base_url,
                headers=auth_headers,
                method="GET",
                path=f"/rest/api/2/issue/{key}",
                params={
                    "fields": (
                        "summary,description,status,issuetype,project,priority,"
                        "assignee,reporter,labels,updated,created"
                    )
                },
            )
        elif tool_name == "jira_list_projects":
            data = await _jira_request(base_url=base_url, headers=auth_headers, method="GET", path="/rest/api/2/project", params={"maxResults": _limit(arguments.get("limit"))})
            if isinstance(data, list):
                data = data[:_limit(arguments.get("limit"))]
        elif tool_name == "jira_create_issue":
            project_key, issue_type, summary = (str(arguments.get(key) or "").strip() for key in ("project_key", "issue_type", "summary"))
            if not all((project_key, issue_type, summary)):
                raise ValueError("project_key, issue_type and summary are required")
            fields: dict[str, Any] = {"project": {"key": project_key}, "issuetype": {"name": issue_type}, "summary": summary}
            for key in ("description", "labels"):
                if arguments.get(key) is not None:
                    fields[key] = arguments[key]
            data = await _jira_request(base_url=base_url, headers=auth_headers, method="POST", path="/rest/api/2/issue", body={"fields": fields})
        elif tool_name == "jira_update_issue":
            key, fields = _issue_path_key(arguments.get("issue_key")), arguments.get("fields")
            if not isinstance(fields, dict) or not fields:
                raise ValueError("non-empty fields are required")
            data = await _jira_request(
                base_url=base_url,
                headers=auth_headers,
                method="PUT",
                path=f"/rest/api/2/issue/{key}",
                body={"fields": fields},
            )
        elif tool_name == "jira_transition_issue":
            key = _issue_path_key(arguments.get("issue_key"))
            transition_id = str(arguments.get("transition_id") or "").strip()
            if not transition_id:
                raise ValueError("transition_id is required")
            data = await _jira_request(
                base_url=base_url,
                headers=auth_headers,
                method="POST",
                path=f"/rest/api/2/issue/{key}/transitions",
                body={"transition": {"id": transition_id}},
            )
        elif tool_name == "jira_add_comment":
            key, body = _issue_path_key(arguments.get("issue_key")), str(arguments.get("body") or "").strip()
            if not body:
                raise ValueError("body is required")
            data = await _jira_request(
                base_url=base_url,
                headers=auth_headers,
                method="POST",
                path=f"/rest/api/2/issue/{key}/comment",
                body={"body": body},
            )
        else:
            return _jsonrpc_err(rpc_id, -32601, f"Unknown tool: {tool_name}")
        return _jsonrpc_ok(rpc_id, _tool_result(data))
    except (ValueError, httpx.HTTPError) as exc:
        logger.warning(
            "jira_mcp_request_failed rpc_id=%s method=%s tool=%s error_type=%s error=%s",
            rpc_id,
            method,
            tool_name if method == "tools/call" else None,
            type(exc).__name__,
            _safe_error_message(exc),
        )
        return _jsonrpc_err(rpc_id, -32000, "Jira MCP request failed")
