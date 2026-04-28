from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.agents.contracts import OperationCredentialContext
from app.models.tool_instance import ToolInstance
from app.services.credential_scope_resolver import (
    CredentialStrategy,
    CredentialScopeResolver,
    OperationFlags,
)
from app.services.credential_service import CredentialService


class CredentialsUnavailableError(RuntimeError):
    """Raised when strict credential strategy cannot resolve credentials."""

    def __init__(
        self,
        *,
        tool_slug: str,
        operation: str,
        scope_required: str,
        reason: str,
    ) -> None:
        super().__init__(reason)
        self.tool_slug = tool_slug
        self.operation = operation
        self.scope_required = scope_required
        self.reason = reason


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
        tool_slug: Optional[str] = None,
        operation: Optional[str] = None,
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
        strategy = self.scope_resolver.resolve(flags)
        strategy_value = strategy.value

        if self.mcp_credential_broker_enabled:
            reference = await self.credential_service.resolve_credential_reference(
                instance_id=instance.id,
                strategy=strategy_value,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            if not reference:
                self._raise_if_strict_missing(
                    strategy=strategy,
                    instance=instance,
                    tool_slug=tool_slug,
                    operation=operation,
                )
                return None
            payload = {}
            get_decrypted = getattr(self.credential_service, "get_decrypted_credentials", None)
            if callable(get_decrypted):
                try:
                    decrypted = await get_decrypted(reference.credential_id)
                    payload = dict(getattr(decrypted, "payload", {}) or {})
                except Exception:
                    # Keep broker flow available even if payload backfill fails.
                    payload = {}
            return OperationCredentialContext(
                auth_type=reference.auth_type,
                payload=payload,
                credential_id=str(reference.credential_id),
                owner_type=reference.owner_type,
            )

        decrypted = await self.credential_service.resolve_credentials(
            instance_id=instance.id,
            strategy=strategy_value,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        if not decrypted:
            self._raise_if_strict_missing(
                strategy=strategy,
                instance=instance,
                tool_slug=tool_slug,
                operation=operation,
            )
            return None
        return OperationCredentialContext(
            auth_type=decrypted.auth_type,
            payload=decrypted.payload,
            credential_id=str(decrypted.credential_id),
            owner_type=decrypted.owner_type,
        )

    @staticmethod
    def _raise_if_strict_missing(
        *,
        strategy: CredentialStrategy,
        instance: ToolInstance,
        tool_slug: Optional[str],
        operation: Optional[str],
    ) -> None:
        if strategy not in {CredentialStrategy.USER_ONLY, CredentialStrategy.PLATFORM_ONLY}:
            return
        scope_required = "user" if strategy == CredentialStrategy.USER_ONLY else "platform"
        op = str(operation or tool_slug or instance.slug)
        raise CredentialsUnavailableError(
            tool_slug=str(tool_slug or instance.slug),
            operation=op,
            scope_required=scope_required,
            reason=(
                f"Operation '{op}' requires {scope_required} credentials, "
                "but none are configured."
            ),
        )
