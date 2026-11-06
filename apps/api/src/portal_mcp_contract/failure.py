"""Typed, bounded and secret-aware diagnostics for MCP tool failures."""
from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MCP_FAILURE_VERSION = 1
_MAX_DEPTH = 8
_MAX_ITEMS = 200
_MAX_TEXT = 8000
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SENSITIVE_KEYS = frozenset({
    "authorization", "proxy_authorization", "password", "passwd", "secret", "cookie",
    "token", "access_token", "refresh_token", "id_token", "api_token", "session_token",
    "client_token", "personal_token", "personal_access_token", "jira_personal_token",
    "confluence_personal_token", "api_key", "apikey", "client_secret", "private_key",
    "dsn", "db_dsn", "database_url", "jira_token", "confluence_token",
})
_PRIVATE_REASONING_KEYS = frozenset({
    "reasoning", "reasoning_content", "chain_of_thought", "hidden_chain_of_thought", "private_reasoning",
})
_BEARER = re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9+/=_\-.]+")
_SECRET_KV = re.compile(r'''(?i)(["']?([a-z][a-z0-9_.-]*)["']?\s*[:=]\s*["']?)([^\s,"';&}]+)''')
_URL_AUTH = re.compile(r"(?i)(https?://)[^:/@\s]+:[^/@\s]+@")
_SECRET_QUERY = re.compile(r"(?i)([?&]([^=&#]+)=)([^&#\s]+)")


def is_sensitive_key(key: Any) -> bool:
    """Match credential value fields without hiding diagnostic names like expected_token."""
    normalized = _CAMEL_BOUNDARY.sub("_", str(key)).lower().replace("-", "_")
    compact = re.sub(r"[^a-z0-9_]", "", normalized)
    return normalized in _SENSITIVE_KEYS or compact in {"proxyauthorization", "privatekey", "databaseurl"}


def _redact_assignment(match: re.Match[str]) -> str:
    if is_sensitive_key(match.group(2)):
        return f"{match.group(1)}[redacted]"
    return match.group(0)


class MCPFailureKind(str, Enum):
    TOOL = "tool"
    RPC = "rpc"
    HTTP = "http"
    TRANSPORT = "transport"
    PROTOCOL = "protocol"


class MCPFailureCategory(str, Enum):
    INPUT = "input"
    AUTH = "auth"
    ACCESS = "access"
    AVAILABILITY = "availability"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"


def public_user_message(category: MCPFailureCategory) -> str:
    return {
        MCPFailureCategory.INPUT: "The source rejected the search request.",
        MCPFailureCategory.AUTH: "The source rejected its authentication credentials.",
        MCPFailureCategory.ACCESS: "The account does not have access to the requested data.",
        MCPFailureCategory.AVAILABILITY: "The source is currently unavailable.",
        MCPFailureCategory.RATE_LIMIT: "The source is temporarily limiting requests.",
        MCPFailureCategory.UNKNOWN: "The source request failed.",
    }[category]


class MCPFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = MCP_FAILURE_VERSION
    kind: MCPFailureKind
    category: MCPFailureCategory = MCPFailureCategory.UNKNOWN
    code: str | int | None = None
    message: str = Field(max_length=_MAX_TEXT)
    details: Any = None
    request_id: str | None = Field(default=None, max_length=120)
    stage: str | None = Field(default=None, max_length=80)
    http_status: int | None = Field(default=None, ge=100, le=599)
    rpc_code: str | int | None = None
    rpc_data: Any = None
    user_message: str = Field(default="The tool call failed.", max_length=500)

    @field_validator("code", "rpc_code", mode="before")
    @classmethod
    def bound_codes(cls, value: Any) -> Any:
        return _redact_text(value, ()) if isinstance(value, str) else value

    def bounded_dump(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        if len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) > 24000:
            payload["details"] = {"_truncated": True}
            payload["rpc_data"] = None
        return payload


def _redact_text(value: str, secrets: tuple[str, ...]) -> str:
    result = _SECRET_KV.sub(_redact_assignment, _BEARER.sub("[redacted]", value))
    result = _URL_AUTH.sub(r"\1[redacted]@", result)
    result = _SECRET_QUERY.sub(lambda match: f"{match.group(1)}[redacted]" if is_sensitive_key(match.group(2)) else match.group(0), result)
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[redacted]")
    if len(result) > _MAX_TEXT:
        return result[:_MAX_TEXT - 14] + " [truncated]"
    return result


def safe_diagnostic(value: Any, *, secrets: tuple[str, ...] = (), depth: int = 0) -> Any:
    """Preserve diagnostic JSON while bounding size and removing credential material."""
    if depth > _MAX_DEPTH:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _redact_text(value, secrets)
    if isinstance(value, list):
        items = [safe_diagnostic(item, secrets=secrets, depth=depth + 1) for item in value[:_MAX_ITEMS]]
        if len(value) > _MAX_ITEMS:
            items.append({"_truncated": True, "remaining_items": len(value) - _MAX_ITEMS})
        return items
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_ITEMS:
                result["_truncated"] = True
                break
            name = str(key)[:200]
            normalized_name = _CAMEL_BOUNDARY.sub("_", name).lower().replace("-", "_")
            if normalized_name in _PRIVATE_REASONING_KEYS:
                result[name] = "[redacted]"
                continue
            result[name] = "[redacted]" if is_sensitive_key(name) else safe_diagnostic(
                item, secrets=secrets, depth=depth + 1
            )
        return result
    return _redact_text(str(value), secrets)


def normalize_failure(value: Any, *, secrets: tuple[str, ...] = ()) -> dict[str, Any] | None:
    """Validate the versioned envelope and re-sanitize all source-controlled strings."""
    try:
        failure = MCPFailure.model_validate(value)
    except Exception:
        return None
    payload = failure.model_dump(mode="python")
    payload["code"] = safe_diagnostic(failure.code, secrets=secrets)
    payload["rpc_code"] = safe_diagnostic(failure.rpc_code, secrets=secrets)
    payload["message"] = str(safe_diagnostic(failure.message, secrets=secrets))
    payload["details"] = safe_diagnostic(failure.details, secrets=secrets)
    payload["rpc_data"] = safe_diagnostic(failure.rpc_data, secrets=secrets)
    payload["request_id"] = safe_diagnostic(failure.request_id, secrets=secrets)
    payload["stage"] = safe_diagnostic(failure.stage, secrets=secrets)
    payload["user_message"] = public_user_message(failure.category)
    return MCPFailure.model_validate(payload).bounded_dump()

