from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx


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

    async def resolve(self, access: Dict[str, Any]) -> ResolvedCredential:
        if not isinstance(access, dict):
            raise ValueError("credential_access must be an object")
        token = str(access.get("token") or "").strip()
        resolve_url = str(access.get("resolve_url") or "").strip()
        if not token:
            raise ValueError("credential_access.token is required")
        if not resolve_url:
            raise ValueError("credential_access.resolve_url is required")

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            response = await client.post(resolve_url, headers=headers)
        if response.status_code >= 400:
            raise ValueError(
                f"Secret broker resolve failed with HTTP {response.status_code}: {response.text[:300]}"
            )
        data = response.json()
        return ResolvedCredential(
            credential_id=str(data.get("credential_id") or ""),
            instance_id=str(data.get("instance_id") or ""),
            auth_type=str(data.get("auth_type") or ""),
            owner_type=str(data.get("owner_type") or ""),
            payload=dict(data.get("payload") or {}),
            expires_at=int(data.get("expires_at") or 0),
        )
