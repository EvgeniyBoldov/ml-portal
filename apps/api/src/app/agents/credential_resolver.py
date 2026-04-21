from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.agents.contracts import OperationCredentialContext
from app.models.tool_instance import ToolInstance
from app.services.credential_scope_resolver import (
    CredentialScopeResolver,
    OperationFlags,
)
from app.services.credential_service import CredentialService


class RuntimeCredentialResolver:
    """Resolves execution credentials for runtime operations.

    Strategy selection is delegated to `CredentialScopeResolver` so that
    risk-aware scope cascades (user-first for risky ops, platform-first for
    read-only ones) can evolve without touching this resolver.
    """

    def __init__(
        self,
        credential_service: CredentialService,
        *,
        mcp_credential_broker_enabled: bool,
        scope_resolver: Optional[CredentialScopeResolver] = None,
    ) -> None:
        self.credential_service = credential_service
        self.mcp_credential_broker_enabled = bool(mcp_credential_broker_enabled)
        self.scope_resolver = scope_resolver or CredentialScopeResolver()

    async def resolve_for_execution(
        self,
        instance: ToolInstance,
        *,
        user_id: UUID,
        tenant_id: UUID,
        credential_scope: str = "auto",
        risk_level: str = "safe",
        side_effects: bool = False,
        requires_confirmation: bool = False,
    ) -> Optional[OperationCredentialContext]:
        if instance.is_local:
            return None

        flags = OperationFlags(
            risk_level=risk_level,  # type: ignore[arg-type]
            side_effects=bool(side_effects),
            requires_confirmation=bool(requires_confirmation),
            credential_scope=credential_scope,  # type: ignore[arg-type]
        )
        strategy = self.scope_resolver.resolve_strategy(flags)

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
