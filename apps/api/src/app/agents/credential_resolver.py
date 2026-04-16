from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.agents.contracts import OperationCredentialContext
from app.models.tool_instance import ToolInstance
from app.services.credential_service import CredentialService

PLATFORM_CREDENTIAL_STRATEGY = "PLATFORM_ONLY"


class RuntimeCredentialResolver:
    """Resolves execution credentials for runtime operations.

    Current policy is intentionally strict and simple:
    - resolve only platform-level credentials
    - ignore operation credential_scope for now
    """

    def __init__(
        self,
        credential_service: CredentialService,
        *,
        mcp_credential_broker_enabled: bool,
    ) -> None:
        self.credential_service = credential_service
        self.mcp_credential_broker_enabled = bool(mcp_credential_broker_enabled)

    async def resolve_for_execution(
        self,
        instance: ToolInstance,
        *,
        user_id: UUID,
        tenant_id: UUID,
        credential_scope: str = "any",
    ) -> Optional[OperationCredentialContext]:
        if instance.is_local:
            return None

        strategy = PLATFORM_CREDENTIAL_STRATEGY
        if self.mcp_credential_broker_enabled:
            reference = await self.credential_service.resolve_credential_reference(
                instance_id=instance.id,
                strategy=strategy,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            if not reference:
                return None
            return OperationCredentialContext(
                auth_type=reference.auth_type,
                payload={},
                credential_id=str(reference.credential_id),
                owner_type=reference.owner_type,
            )

        decrypted = await self.credential_service.resolve_credentials(
            instance_id=instance.id,
            strategy=strategy,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        if not decrypted:
            return None
        return OperationCredentialContext(
            auth_type=decrypted.auth_type,
            payload=decrypted.payload,
            credential_id=str(decrypted.credential_id),
            owner_type=decrypted.owner_type,
        )
