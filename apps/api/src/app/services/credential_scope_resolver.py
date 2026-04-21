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


RiskLevel = Literal["safe", "write", "destructive"]
CredentialScope = Literal["platform", "user", "auto"]

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

    risk_level: RiskLevel = "safe"
    side_effects: bool = False
    requires_confirmation: bool = False
    credential_scope: CredentialScope = "auto"

    @property
    def is_risky(self) -> bool:
        """Operation changes state or requires explicit human confirmation."""
        return (
            bool(self.side_effects)
            or self.risk_level in ("write", "destructive")
            or self.requires_confirmation
        )


class CredentialScopeResolver:
    """Map `OperationFlags` → repository strategy string."""

    _EXPLICIT_SCOPE_MAP: dict[str, Strategy] = {
        "user": "USER_ONLY",
        "platform": "PLATFORM_ONLY",
    }

    def resolve_strategy(self, flags: OperationFlags) -> Strategy:
        """Return the credential lookup strategy for the given flags.

        Rules (in order):
        1. Explicit `credential_scope` always wins, unless it is "auto".
        2. "auto" + risky operation → prefer user-owned credentials
           (cascade user → tenant → platform).
        3. "auto" + safe operation → prefer platform credentials,
           fall back to tenant, then user (cascade platform → tenant → user).
        """
        explicit = self._EXPLICIT_SCOPE_MAP.get(flags.credential_scope)
        if explicit is not None:
            return explicit
        if flags.is_risky:
            return "ANY"
        return "PLATFORM_FIRST"
