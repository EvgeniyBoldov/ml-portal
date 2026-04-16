from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError, ValidationError
from app.models.credential_set import Credential
from app.services.credential_service import CredentialService, DecryptedCredentials


@dataclass
class MCPCredentialAccessContext:
    credential_id: str
    auth_type: str
    owner_type: str
    token: str
    resolve_url: str
    expires_at: int


@dataclass
class ResolvedMCPCredential:
    credential_id: UUID
    instance_id: UUID
    auth_type: str
    owner_type: str
    payload: Dict[str, Any]
    expires_at: int


class MCPCredentialBrokerService:
    """Issues and resolves short-lived MCP credential access tokens."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.credential_service = CredentialService(session)
        self.settings = get_settings()

    @staticmethod
    def _signing_key() -> str:
        s = get_settings()
        if s.JWT_ALGORITHM.startswith("RS") or s.JWT_ALGORITHM.startswith("ES"):
            if not s.JWT_PRIVATE_KEY:
                raise ValueError(f"JWT_PRIVATE_KEY required for {s.JWT_ALGORITHM}")
            return s.JWT_PRIVATE_KEY
        return s.JWT_SECRET

    @staticmethod
    def _verify_key() -> str:
        s = get_settings()
        if s.JWT_ALGORITHM.startswith("RS") or s.JWT_ALGORITHM.startswith("ES"):
            if not s.JWT_PUBLIC_KEY:
                raise ValueError(f"JWT_PUBLIC_KEY required for {s.JWT_ALGORITHM}")
            return s.JWT_PUBLIC_KEY
        return s.JWT_SECRET

    @classmethod
    def build_resolve_url(cls) -> str:
        s = get_settings()
        return f"{s.MCP_CREDENTIAL_BROKER_BASE_URL.rstrip('/')}{s.MCP_CREDENTIAL_BROKER_RESOLVE_PATH}"

    @classmethod
    def issue_access_context(
        cls,
        *,
        user_id: UUID | str,
        tenant_id: UUID | str,
        provider_instance_id: Optional[str],
        provider_instance_slug: Optional[str],
        data_instance_id: Optional[str],
        data_instance_slug: Optional[str],
        operation_slug: str,
        mcp_tool_name: Optional[str],
        credential_id: str,
        auth_type: str,
        owner_type: str,
    ) -> MCPCredentialAccessContext:
        s = get_settings()
        now = int(time.time())
        exp = now + max(15, int(s.MCP_CREDENTIAL_TOKEN_TTL_SECONDS or 90))
        payload: Dict[str, Any] = {
            "sub": str(user_id),
            "tenant_id": str(tenant_id),
            "iss": s.JWT_ISSUER,
            "aud": s.MCP_CREDENTIAL_BROKER_AUDIENCE,
            "iat": now,
            "exp": exp,
            "jti": str(uuid.uuid4()),
            "type": "mcp_credential_access",
            "credential_id": credential_id,
            "auth_type": auth_type,
            "owner_type": owner_type,
            "provider_instance_id": provider_instance_id,
            "provider_instance_slug": provider_instance_slug,
            "data_instance_id": data_instance_id,
            "data_instance_slug": data_instance_slug,
            "operation_slug": operation_slug,
            "mcp_tool_name": mcp_tool_name,
        }
        headers = {"kid": s.JWT_KID} if s.JWT_KID else None
        token = jwt.encode(payload, cls._signing_key(), algorithm=s.JWT_ALGORITHM, headers=headers)
        return MCPCredentialAccessContext(
            credential_id=credential_id,
            auth_type=auth_type,
            owner_type=owner_type,
            token=token,
            resolve_url=cls.build_resolve_url(),
            expires_at=exp,
        )

    @classmethod
    def decode_access_token(cls, token: str) -> Dict[str, Any]:
        s = get_settings()
        try:
            payload = jwt.decode(
                token,
                cls._verify_key(),
                algorithms=[s.JWT_ALGORITHM],
                audience=s.MCP_CREDENTIAL_BROKER_AUDIENCE,
                issuer=s.JWT_ISSUER,
            )
        except jwt.ExpiredSignatureError as exc:
            raise UnauthorizedError("MCP credential access token expired") from exc
        except jwt.InvalidTokenError as exc:
            raise UnauthorizedError(f"Invalid MCP credential access token: {exc}") from exc

        if payload.get("type") != "mcp_credential_access":
            raise UnauthorizedError("Invalid MCP credential access token type")
        if not payload.get("credential_id"):
            raise UnauthorizedError("MCP credential access token missing credential_id")
        return payload

    async def resolve_access_token(self, token: str) -> ResolvedMCPCredential:
        claims = self.decode_access_token(token)

        cred_id = UUID(str(claims["credential_id"]))
        credential: Credential = await self.credential_service.get_credentials(cred_id)
        decrypted: DecryptedCredentials = await self.credential_service.get_decrypted_credentials(cred_id)

        expected_provider = claims.get("provider_instance_id")
        if expected_provider and str(credential.instance_id) != str(expected_provider):
            raise UnauthorizedError("Credential does not belong to requested provider instance")

        owner_type = str(claims.get("owner_type") or "")
        subject_user = claims.get("sub")
        subject_tenant = claims.get("tenant_id")
        if owner_type == "user" and str(credential.owner_user_id or "") != str(subject_user or ""):
            raise UnauthorizedError("Credential owner mismatch (user)")
        if owner_type == "tenant" and str(credential.owner_tenant_id or "") != str(subject_tenant or ""):
            raise UnauthorizedError("Credential owner mismatch (tenant)")
        if owner_type == "platform" and not bool(credential.owner_platform):
            raise UnauthorizedError("Credential owner mismatch (platform)")

        expected_auth_type = claims.get("auth_type")
        if expected_auth_type and str(expected_auth_type) != str(decrypted.auth_type):
            raise ValidationError("Credential auth_type mismatch")

        return ResolvedMCPCredential(
            credential_id=credential.id,
            instance_id=credential.instance_id,
            auth_type=decrypted.auth_type,
            owner_type=decrypted.owner_type,
            payload=decrypted.payload,
            expires_at=int(claims.get("exp") or 0),
        )
