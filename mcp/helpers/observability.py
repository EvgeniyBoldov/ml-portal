from __future__ import annotations

import logging
import re
import uuid
from typing import Optional


REQUEST_ID_HEADER = "x-portal-request-id"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,100}$")


def normalize_request_id(value: Optional[str]) -> str:
    """Accept a bounded opaque correlation id or generate one locally."""
    candidate = str(value or "").strip()
    return candidate if _REQUEST_ID_RE.fullmatch(candidate) else uuid.uuid4().hex


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
) -> None:
    """Emit bounded operational context without request or response contents."""
    log = logger.warning if outcome == "failed" else logger.info
    log(
        "mcp_request_%s request_id=%s server=%s method=%s tool=%s stage=%s "
        "duration_ms=%s error_type=%s http_status=%s rpc_code=%s",
        outcome,
        request_id,
        server,
        method,
        tool or "-",
        stage or "-",
        duration_ms if duration_ms is not None else "-",
        error_type or "-",
        http_status if http_status is not None else "-",
        rpc_code if rpc_code is not None else "-",
    )


class BrokerHTTPError(ValueError):
    def __init__(self, status_code: int) -> None:
        super().__init__("Secret broker resolve failed")
        self.status_code = status_code


class UpstreamHTTPError(ValueError):
    def __init__(self, status_code: int) -> None:
        super().__init__("MCP upstream returned an HTTP error")
        self.status_code = status_code
