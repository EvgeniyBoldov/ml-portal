from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any, Dict, Optional

import httpx

from helpers.observability import (
    BrokerHTTPError,
    log_mcp_event,
    normalize_request_id,
    safe_error_detail,
    safe_target,
)


logger = logging.getLogger("mcp.credential_broker")


@dataclass
class ResolvedCredential:
    credential_id: str
    instance_id: str
    auth_type: str
    owner_type: str
    payload: Dict[str, Any]
    expires_at: int


def extract_credential_access(arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(arguments, dict):
        return None
    access = arguments.get("credential_access")
    if isinstance(access, dict):
        return access
    instance_context = arguments.get("instance_context")
    if isinstance(instance_context, dict):
        nested = instance_context.get("credential_access")
        if isinstance(nested, dict):
            return nested
    return None


class SecretBrokerClient:
    """Client for resolving short-lived MCP credential access tokens."""

    def __init__(self, *, timeout_s: int = 10) -> None:
        self.timeout_s = timeout_s

    async def resolve(
        self,
        access: Dict[str, Any],
        *,
        request_id: str = "",
        server: str = "mcp",
        method: str = "tools/call",
        tool: str = "",
        data_instance_id: str = "",
        provider_instance_id: str = "",
    ) -> ResolvedCredential:
        if not isinstance(access, dict):
            raise ValueError("credential_access must be an object")
        token = str(access.get("token") or "").strip()
        resolve_url = str(access.get("resolve_url") or "").strip()
        if not token:
            raise ValueError("credential_access.token is required")
        if not resolve_url:
            raise ValueError("credential_access.resolve_url is required")

        request_id = normalize_request_id(request_id)
        credential_id = str(access.get("credential_id") or "")
        started = time.monotonic()
        log_mcp_event(
            logger,
            outcome="started",
            request_id=request_id,
            server=server,
            method=method,
            tool=tool,
            stage="broker_request",
            target=safe_target(resolve_url),
            data_instance_id=data_instance_id or str(access.get("data_instance_id") or ""),
            provider_instance_id=provider_instance_id or str(access.get("provider_instance_id") or ""),
            credential_id=credential_id,
        )
        headers = {"Authorization": f"Bearer {token}", "x-portal-request-id": request_id}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as client:
                response = await client.post(resolve_url, headers=headers)
        except httpx.HTTPError as exc:
            log_mcp_event(
                logger,
                outcome="failed",
                request_id=request_id,
                server=server,
                method=method,
                tool=tool,
                stage="broker_request",
                target=safe_target(resolve_url),
                data_instance_id=data_instance_id or str(access.get("data_instance_id") or ""),
                provider_instance_id=provider_instance_id or str(access.get("provider_instance_id") or ""),
                credential_id=credential_id,
                duration_ms=int((time.monotonic() - started) * 1000),
                error_type=type(exc).__name__,
                error_detail=safe_error_detail(exc),
            )
            raise
        if response.status_code >= 400:
            # Never retain or log a broker response body: it may contain
            # credential or identity data. Preserve only the status code.
            log_mcp_event(
                logger,
                outcome="failed",
                request_id=request_id,
                server=server,
                method=method,
                tool=tool,
                stage="broker_response",
                target=safe_target(resolve_url),
                data_instance_id=data_instance_id or str(access.get("data_instance_id") or ""),
                provider_instance_id=provider_instance_id or str(access.get("provider_instance_id") or ""),
                credential_id=credential_id,
                duration_ms=int((time.monotonic() - started) * 1000),
                http_status=response.status_code,
                error_type="BrokerHTTPError",
            )
            raise BrokerHTTPError(response.status_code)
        try:
            data = response.json()
        except ValueError as exc:
            log_mcp_event(
                logger,
                outcome="failed",
                request_id=request_id,
                server=server,
                method=method,
                tool=tool,
                stage="broker_decode",
                target=safe_target(resolve_url),
                data_instance_id=data_instance_id or str(access.get("data_instance_id") or ""),
                provider_instance_id=provider_instance_id or str(access.get("provider_instance_id") or ""),
                credential_id=credential_id,
                duration_ms=int((time.monotonic() - started) * 1000),
                http_status=response.status_code,
                error_type=type(exc).__name__,
            )
            raise
        if not isinstance(data, dict):
            log_mcp_event(
                logger,
                outcome="failed",
                request_id=request_id,
                server=server,
                method=method,
                tool=tool,
                stage="broker_decode",
                target=safe_target(resolve_url),
                data_instance_id=data_instance_id or str(access.get("data_instance_id") or ""),
                provider_instance_id=provider_instance_id or str(access.get("provider_instance_id") or ""),
                credential_id=credential_id,
                duration_ms=int((time.monotonic() - started) * 1000),
                http_status=response.status_code,
                error_type="InvalidBrokerPayload",
            )
            raise ValueError("Secret broker returned an invalid response")
        resolved = ResolvedCredential(
            credential_id=str(data.get("credential_id") or ""),
            instance_id=str(data.get("instance_id") or ""),
            auth_type=str(data.get("auth_type") or ""),
            owner_type=str(data.get("owner_type") or ""),
            payload=dict(data.get("payload") or {}),
            expires_at=int(data.get("expires_at") or 0),
        )
        log_mcp_event(
            logger,
            outcome="completed",
            request_id=request_id,
            server=server,
            method=method,
            tool=tool,
            stage="broker_resolved",
            target=safe_target(resolve_url),
            data_instance_id=data_instance_id or resolved.instance_id,
            provider_instance_id=provider_instance_id or str(access.get("provider_instance_id") or ""),
            credential_id=resolved.credential_id,
            auth_type=resolved.auth_type,
            duration_ms=int((time.monotonic() - started) * 1000),
            http_status=response.status_code,
        )
        return resolved
