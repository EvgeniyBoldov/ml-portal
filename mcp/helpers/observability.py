from __future__ import annotations

import logging
import re
import uuid
from typing import Optional
from urllib.parse import urlsplit


REQUEST_ID_HEADER = "x-portal-request-id"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(authorization|token|pat|api[_-]?token|access[_-]?token|api[_-]?key|password|secret)"
    r"(\s*[\"']?\s*[:=]\s*)(?:[\"'][^\"']*[\"']|(?:bearer|basic)\s+[^\s,;]+|[^\s,;]+)"
)


def normalize_request_id(value: Optional[str]) -> str:
    """Accept a bounded opaque correlation id or generate one locally."""
    candidate = str(value or "").strip()
    return candidate if _REQUEST_ID_RE.fullmatch(candidate) else uuid.uuid4().hex


def _safe_log_atom(value: object, *, limit: int = 160) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    return re.sub(r"[^A-Za-z0-9_.:/@+-]", "_", text)[:limit] or "-"


def safe_target(value: str) -> str:
    """Return a URL origin only; never include credentials, path or query."""
    try:
        parsed = urlsplit(str(value or ""))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return "unknown"
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{host}{port}"
    except (TypeError, ValueError):
        return "unknown"


def safe_error_detail(exc: BaseException) -> str:
    """Keep useful transport details while removing common secret-shaped values."""
    cause = exc.__cause__ or exc.__context__
    if cause is not None:
        errno = getattr(cause, "errno", None)
        strerror = getattr(cause, "strerror", None)
        if errno is not None or strerror:
            detail = f"cause={type(cause).__name__} errno={errno or '-'} reason={strerror or '-'}"
        else:
            detail = f"cause={type(cause).__name__}"
    else:
        detail = str(exc)
    detail = detail.replace("\n", " ").replace("\r", " ")
    detail = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}***", detail)
    # URL paths and query values can contain Jira keys, prompts, or user data.
    detail = re.sub(r"https?://[^\s\"']+", "<url>", detail, flags=re.IGNORECASE)
    return detail[:240]


def log_mcp_event(
    logger: logging.Logger,
    *,
    outcome: str,
    request_id: str,
    server: str,
    method: str,
    tool: str = "",
    stage: str = "",
    duration_ms: Optional[int] = None,
    error_type: str = "",
    http_status: Optional[int] = None,
    rpc_code: Optional[int] = None,
    rpc_message: str = "",
    target: str = "",
    target_path: str = "",
    data_instance_id: str = "",
    provider_instance_id: str = "",
    credential_id: str = "",
    auth_type: str = "",
    auth_headers: str = "",
    error_detail: str = "",
    response_bytes: Optional[int] = None,
) -> None:
    """Emit bounded operational context without request or response contents."""
    log = logger.warning if outcome == "failed" else logger.info
    log(
        "mcp_request_%s request_id=%s server=%s method=%s tool=%s stage=%s "
        "duration_ms=%s target=%s target_path=%s data_instance_id=%s provider_instance_id=%s "
        "credential_id=%s auth_type=%s auth_headers=%s http_status=%s rpc_code=%s "
        "rpc_message=%s response_bytes=%s error_type=%s error_detail=%s",
        outcome,
        normalize_request_id(request_id),
        _safe_log_atom(server),
        _safe_log_atom(method),
        _safe_log_atom(tool),
        _safe_log_atom(stage),
        duration_ms if duration_ms is not None else "-",
        _safe_log_atom(target),
        _safe_log_atom(target_path),
        _safe_log_atom(data_instance_id),
        _safe_log_atom(provider_instance_id),
        _safe_log_atom(credential_id),
        _safe_log_atom(auth_type),
        _safe_log_atom(auth_headers),
        http_status if http_status is not None else "-",
        rpc_code if rpc_code is not None else "-",
        _safe_log_atom(rpc_message),
        response_bytes if response_bytes is not None else "-",
        _safe_log_atom(error_type),
        str(error_detail or "-").replace("\n", " ").replace("\r", " ")[:240],
    )


class BrokerHTTPError(ValueError):
    def __init__(self, status_code: int) -> None:
        super().__init__("Secret broker resolve failed")
        self.status_code = status_code


class UpstreamHTTPError(ValueError):
    def __init__(self, status_code: int) -> None:
        super().__init__("MCP upstream returned an HTTP error")
        self.status_code = status_code
