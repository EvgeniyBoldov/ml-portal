"""
CredentialScopeResolver — single place that decides which credential scope
cascade to apply for a given operation.

Inputs: per-operation runtime flags (risk_level, side_effects,
requires_confirmation, credential_scope).

Output: one of the strategies understood by
`CredentialSetRepository.resolve_for_instance`:

    USER_ONLY, TENANT_ONLY, PLATFORM_ONLY,
    USER_THEN_TENANT, TENANT_THEN_PLATFORM,
    ANY (= user → tenant → platform),
    PLATFORM_FIRST (= platform → tenant → user).

The resolver is intentionally a pure function today; it exists as a dedicated
service so behaviour can be swapped (config-driven, policy-driven, LLM-advised)
without touching the runtime credential resolver.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RiskLevel = Literal["low", "medium", "high"]
SideEffects = Literal["none", "write", "destructive"]
CredentialScope = Literal[
    "any", "user_only", "tenant_only", "platform_only", "any_non_user"
]

Strategy = Literal[
    "USER_ONLY",
    "TENANT_ONLY",
    "PLATFORM_ONLY",
    "USER_THEN_TENANT",
    "TENANT_THEN_PLATFORM",
    "ANY",
    "PLATFORM_FIRST",
]


@dataclass(frozen=True, slots=True)
class OperationFlags:
    """Runtime contract of a single resolved operation.

    Defaults match the current behaviour when no flags are known:
    cheap, read-only, no confirmation, any credential scope.
    """

    risk_level: RiskLevel = "low"
    side_effects: SideEffects = "none"
    requires_confirmation: bool = False
    credential_scope: CredentialScope = "any"

    @property
    def is_risky(self) -> bool:
        """Operation changes state or requires explicit human confirmation."""
        return (
            self.side_effects in ("write", "destructive")
            or self.risk_level in ("medium", "high")
            or self.requires_confirmation
        )


class CredentialScopeResolver:
    """Map `OperationFlags` → repository strategy string."""

    _EXPLICIT_SCOPE_MAP: dict[str, Strategy] = {
        "user_only": "USER_ONLY",
        "tenant_only": "TENANT_ONLY",
        "platform_only": "PLATFORM_ONLY",
        "any_non_user": "TENANT_THEN_PLATFORM",
    }

    def resolve_strategy(self, flags: OperationFlags) -> Strategy:
        """Return the credential lookup strategy for the given flags.

        Rules (in order):
        1. Explicit `credential_scope` always wins, unless it is "any".
        2. "any" + risky operation → prefer user-owned credentials
           (cascade user → tenant → platform).
        3. "any" + safe operation → prefer platform credentials,
           fall back to tenant, then user (cascade platform → tenant → user).
        """
        explicit = self._EXPLICIT_SCOPE_MAP.get(flags.credential_scope)
        if explicit is not None:
            return explicit
        if flags.is_risky:
            return "ANY"
        return "PLATFORM_FIRST"
