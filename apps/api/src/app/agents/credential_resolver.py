from __future__ import annotations

import json
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
from app.core.logging import get_logger

logger = get_logger(__name__)


def _log_resolution(event: str, *, fields: dict[str, object]) -> None:
    # The console formatter prints only message; retain structured fields too.
    logger.info("%s %s", event, json.dumps(fields, sort_keys=True), extra=fields)


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
    risk-aware scope cascades (user-only for risky ops, user/tenant/platform for
    safe ones) can evolve without touching this resolver.
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
        is_risky: bool = False,
    ) -> Optional[OperationCredentialContext]:
        if instance.is_local:
            return None

        flags = OperationFlags(is_risky=bool(is_risky))
        strategy = self.scope_resolver.resolve(flags)
        strategy_value = strategy.value

        _log_resolution(
            "runtime_credential_resolution_started",
            fields={
                "operation_slug": operation or tool_slug or instance.slug,
                "data_instance_id": str(instance.id),
                "operation_risky": bool(is_risky),
                "credential_strategy": strategy_value,
                "broker_enabled": self.mcp_credential_broker_enabled,
                "user_id": str(user_id),
                "tenant_id": str(tenant_id),
                "required_delivery": "credential_access",
                "credential_source": "data_instance",
            },
        )

        if self.mcp_credential_broker_enabled:
            reference = await self.credential_service.resolve_credential_reference(
                instance_id=instance.id,
                strategy=strategy_value,
                user_id=user_id,
                tenant_id=tenant_id,
            )
            if not reference:
                _log_resolution(
                    "runtime_credential_resolution_completed",
                    fields={
                        "operation_slug": operation or tool_slug or instance.slug,
                        "data_instance_id": str(instance.id),
                        "credential_strategy": strategy_value,
                        "credential_found": False,
                        "broker_enabled": True,
                    },
                )
                self._raise_if_strict_missing(
                    strategy=strategy,
                    instance=instance,
                    tool_slug=tool_slug,
                    operation=operation,
                )
                return None
            _log_resolution(
                "runtime_credential_resolution_completed",
                fields={
                    "operation_slug": operation or tool_slug or instance.slug,
                    "data_instance_id": str(instance.id),
                    "credential_strategy": strategy_value,
                    "credential_found": True,
                    "credential_id": str(reference.credential_id),
                    "credential_owner_type": reference.owner_type,
                    "credential_auth_type": reference.auth_type,
                    "broker_enabled": True,
                },
            )
            return OperationCredentialContext(
                auth_type=reference.auth_type,
                payload={},
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
            _log_resolution(
                "runtime_credential_resolution_completed",
                fields={
                    "operation_slug": operation or tool_slug or instance.slug,
                    "data_instance_id": str(instance.id),
                    "credential_strategy": strategy_value,
                    "credential_found": False,
                    "broker_enabled": False,
                },
            )
            self._raise_if_strict_missing(
                strategy=strategy,
                instance=instance,
                tool_slug=tool_slug,
                operation=operation,
            )
            return None
        _log_resolution(
            "runtime_credential_resolution_completed",
            fields={
                "operation_slug": operation or tool_slug or instance.slug,
                "data_instance_id": str(instance.id),
                "credential_strategy": strategy_value,
                "credential_found": True,
                "credential_id": str(decrypted.credential_id),
                "credential_owner_type": decrypted.owner_type,
                "credential_auth_type": decrypted.auth_type,
                "broker_enabled": False,
            },
        )
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
        if strategy != CredentialStrategy.USER_ONLY:
            return
        scope_required = "user"
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
