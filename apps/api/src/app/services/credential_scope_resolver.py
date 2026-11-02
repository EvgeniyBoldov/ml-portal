"""Resolve credential owner strategy from platform operation risk policy."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CredentialStrategy(str, Enum):
    USER_ONLY = "USER_ONLY"
    USER_FIRST = "USER_FIRST"
    # Kept for non-runtime compatibility callers; MCP runtime uses only the
    # risk-based USER_ONLY / USER_FIRST strategies above.
    PLATFORM_ONLY = "PLATFORM_ONLY"
    PLATFORM_FIRST = "PLATFORM_FIRST"


@dataclass(frozen=True, slots=True)
class OperationFlags:
    is_risky: bool = False


class CredentialScopeResolver:
    """Map platform-owned risk classification to a credential owner cascade.

    Risky operations require a credential owned by the current user. Safe
    operations resolve User > Tenant > Platform. MCP descriptor metadata does
    not participate in this decision.
    """

    def resolve(self, flags: OperationFlags) -> CredentialStrategy:
        return CredentialStrategy.USER_ONLY if flags.is_risky else CredentialStrategy.USER_FIRST

    def resolve_strategy(self, flags: OperationFlags) -> str:
        return self.resolve(flags).value
