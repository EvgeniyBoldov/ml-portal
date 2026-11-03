"""Observe embedded Atlassian auth validation without exposing credential values."""
from __future__ import annotations

import logging
from typing import Any

from helpers.observability import log_mcp_event, normalize_request_id, safe_target

logger = logging.getLogger("mcp.atlassian_auth")


def validation_reason(error: str) -> str:
    """Only emit known categories; upstream errors can contain request secrets."""
    if not error:
        return "no_auth_validation_error"
    if "non-global" in error:
        return "private_ip_blocked"
    if "not in allowed domains" in error:
        return "hostname_not_allowlisted"
    if "DNS resolution" in error:
        return "dns_resolution_failed"
    if "Invalid Jira URL" in error or "Invalid Confluence URL" in error:
        return "invalid_service_url"
    if "Basic" in error or "Email or API token" in error:
        return "invalid_basic_credentials_format"
    return "authentication_validation_failed"


class AtlassianAuthDiagnostics:
    """Wrap ASGI to inspect middleware state, never request/response bodies."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # Upstream copies scope shallowly; provide a request-local shared state
        # so its validation result remains observable even on an early 401.
        scope = {**scope, "state": dict(scope.get("state") or {})}
        headers = dict(scope.get("headers", []))
        request_id = normalize_request_id(headers.get(b"x-portal-request-id", b"").decode("latin-1"))
        status = None

        async def observe_send(message: dict) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, observe_send)
        finally:
            state = scope.get("state") or {}
            error = str(state.get("auth_validation_error") or "")
            url = headers.get(b"x-atlassian-jira-url") or headers.get(b"x-atlassian-confluence-url") or b""
            log_mcp_event(
                logger, outcome="failed" if error or (status and status >= 400) else "completed",
                request_id=request_id, server="embedded-atlassian", method=scope.get("method", ""),
                stage="auth_middleware", http_status=status,
                target=safe_target(url.decode("latin-1")),
                auth_type=str(state.get("portal_source_auth_type") or state.get("user_atlassian_auth_type") or ""),
                error_type=validation_reason(error) if error else "",
                # Presence flags verify the upstream's parsed fields without values.
                error_detail=(
                    f"validation={validation_reason(error)} "
                    f"source_bound={bool(state.get('portal_source_bound'))} "
                    f"username_present={state.get('portal_username_present', bool(state.get('user_atlassian_email')))} "
                    f"api_token_present={state.get('portal_api_token_present', bool(state.get('user_atlassian_api_token')))} "
                    f"token_present={state.get('portal_token_present', bool(state.get('user_atlassian_token')))}"
                ),
            )
