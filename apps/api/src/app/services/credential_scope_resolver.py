"""
CredentialScopeResolver — single place that decides which credential scope
cascade to apply for a given operation.

Inputs: per-operation runtime flags (risk_level, side_effects,
requires_confirmation, credential_scope).

Output: one of the strategies understood by
`CredentialSetRepository.resolve_for_instance`:

    USER_ONLY, PLATFORM_ONLY, PLATFORM_FIRST.

The resolver is intentionally a pure function today; it exists as a dedicated
service so behaviour can be swapped (config-driven, policy-driven, LLM-advised)
without touching the runtime credential resolver.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal


RiskLevel = Literal["safe", "write", "destructive"]
CredentialScope = Literal["platform", "user", "auto"]

Strategy = Literal[
    "USER_ONLY",
    "PLATFORM_ONLY",
    "PLATFORM_FIRST",
]


class CredentialStrategy(str, Enum):
    USER_ONLY = "USER_ONLY"
    PLATFORM_ONLY = "PLATFORM_ONLY"
    PLATFORM_FIRST = "PLATFORM_FIRST"


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
    """Map `OperationFlags` → strict repository strategy."""

    _EXPLICIT_SCOPE_MAP: dict[str, CredentialStrategy] = {
        "user": CredentialStrategy.USER_ONLY,
        "platform": CredentialStrategy.PLATFORM_ONLY,
    }

    def resolve(self, flags: OperationFlags) -> CredentialStrategy:
        """Return strict credential lookup strategy for the given flags.

        Rules (in order):
        1. Explicit `credential_scope` always wins, unless it is "auto".
        2. "auto" + safe read-only operation → PLATFORM_FIRST.
        3. "auto" + side effects/write/destructive → USER_ONLY.
        """
        explicit = self._EXPLICIT_SCOPE_MAP.get(flags.credential_scope)
        if explicit is not None:
            return explicit
        if flags.risk_level == "safe" and not flags.side_effects:
            return CredentialStrategy.PLATFORM_FIRST
        return CredentialStrategy.USER_ONLY

    def resolve_strategy(self, flags: OperationFlags) -> Strategy:
        """Backward-compatible adapter for old call sites."""
        return self.resolve(flags).value  # type: ignore[return-value]
